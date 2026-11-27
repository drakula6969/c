"""
Хранилище в памяти вместо базы данных.

Все клиенты, скриншоты (только метаданные — сами файлы лежат в
config.STORAGE_DIR) и сообщения живут в RAM процесса. Это значит:

- после рестарта сервера список клиентов, история скриншотов и переписка
  очищаются (файлы скриншотов на диске при этом остаются, но без
  метаданных сервер их больше не показывает);
- данные не переживают редеплой на Render — но там и диск эфемерный,
  так что для учебного проекта это не хуже, чем SQLite.

Доступ к данным защищён threading.Lock: FastAPI выполняет sync-эндпоинты
в пуле потоков, а async-эндпоинты и WebSocket — в event loop, поэтому
обычные dict без синхронизации здесь небезопасны.
"""
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Client:
    """Один зарегистрированный компьютер (один запуск с флешки)."""

    id: int
    code: str  # "PC-0001"
    hardware_id: str
    name: Optional[str]
    token: str
    registered_at: datetime
    last_seen: Optional[datetime] = None


@dataclass
class Screenshot:
    id: int
    client_id: int
    filename: str
    created_at: datetime


@dataclass
class Message:
    id: int
    client_id: int
    sender: str  # "admin" | "client"
    text: str
    created_at: datetime


class Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clients: Dict[int, Client] = {}
        self._by_hardware: Dict[str, int] = {}
        self._by_token: Dict[str, int] = {}
        self._screenshots: Dict[int, Screenshot] = {}
        self._messages: Dict[int, Message] = {}
        self._next_client_id = 1
        self._next_screenshot_id = 1
        self._next_message_id = 1

    # ---------- Клиенты ----------

    def register(self, hardware_id: str, name: Optional[str], token: str) -> Client:
        """Регистрирует клиента или возвращает существующего по hardware_id.

        Повторный запуск той же флешки на этом же ПК не плодит дубликаты:
        отдаём те же id/code/token и просто обновляем last_seen.
        """
        with self._lock:
            existing_id = self._by_hardware.get(hardware_id)
            if existing_id is not None:
                client = self._clients[existing_id]
                client.last_seen = utcnow()
                return client

            client_id = self._next_client_id
            self._next_client_id += 1
            client = Client(
                id=client_id,
                code=f"PC-{client_id:04d}",
                hardware_id=hardware_id,
                name=name,
                token=token,
                registered_at=utcnow(),
                last_seen=utcnow(),
            )
            self._clients[client_id] = client
            self._by_hardware[hardware_id] = client_id
            self._by_token[token] = client_id
            return client

    def get_client(self, client_id: int) -> Optional[Client]:
        with self._lock:
            return self._clients.get(client_id)

    def get_by_token(self, token: str) -> Optional[Client]:
        with self._lock:
            client_id = self._by_token.get(token)
            if client_id is None:
                return None
            return self._clients.get(client_id)

    def list_clients(self) -> List[Client]:
        with self._lock:
            return [self._clients[i] for i in sorted(self._clients)]

    def touch(self, client_id: int) -> None:
        """Отмечает клиента как «только что виденный» (heartbeat / WS ping)."""
        with self._lock:
            client = self._clients.get(client_id)
            if client is not None:
                client.last_seen = utcnow()

    # ---------- Скриншоты ----------

    def add_screenshot(self, client_id: int, filename: str, created_at: datetime) -> Screenshot:
        with self._lock:
            shot = Screenshot(
                id=self._next_screenshot_id,
                client_id=client_id,
                filename=filename,
                created_at=created_at,
            )
            self._next_screenshot_id += 1
            self._screenshots[shot.id] = shot
            return shot

    def list_screenshots(self, client_id: int) -> List[Screenshot]:
        with self._lock:
            shots = [s for s in self._screenshots.values() if s.client_id == client_id]
        # Новые сверху, как в прежней версии (ORDER BY created_at DESC).
        shots.sort(key=lambda s: (s.created_at, s.id), reverse=True)
        return shots

    def get_screenshot(self, screenshot_id: int) -> Optional[Screenshot]:
        with self._lock:
            return self._screenshots.get(screenshot_id)

    # ---------- Сообщения ----------

    def add_message(self, client_id: int, sender: str, text: str) -> Message:
        with self._lock:
            msg = Message(
                id=self._next_message_id,
                client_id=client_id,
                sender=sender,
                text=text,
                created_at=utcnow(),
            )
            self._next_message_id += 1
            self._messages[msg.id] = msg
            return msg

    def list_messages(self, client_id: int) -> List[Message]:
        with self._lock:
            msgs = [m for m in self._messages.values() if m.client_id == client_id]
        # Старые сверху, как в прежней версии (ORDER BY created_at ASC).
        msgs.sort(key=lambda m: (m.created_at, m.id))
        return msgs

    def latest_admin_message(self, client_id: int) -> Optional[Message]:
        with self._lock:
            candidates = [
                m
                for m in self._messages.values()
                if m.client_id == client_id and m.sender == "admin"
            ]
        if not candidates:
            return None
        return max(candidates, key=lambda m: (m.created_at, m.id))


# Единственный экземпляр на процесс — импортируется из роутеров и auth.
store = Store()
