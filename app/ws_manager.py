"""
Хранит активные WebSocket-соединения:
- admin_connections — все открытые вкладки админ-панели (их может быть
  несколько), получают live-уведомления: новый скрин, клиент online/offline.
- client_connections — по одному соединению на client_id, используется
  чтобы мгновенно протолкнуть ответ администратора конкретному ПК.

Если проталкивание не удалось (клиент не подключён по WS прямо сейчас),
это не ошибка: клиент всё равно получит ответ через REST
GET /api/me/messages/latest, когда нажмёт кнопку «Ответ».
"""
from typing import Dict, List

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.admin_connections: List[WebSocket] = []
        self.client_connections: Dict[int, WebSocket] = {}

    async def connect_admin(self, ws: WebSocket) -> None:
        await ws.accept()
        self.admin_connections.append(ws)

    def disconnect_admin(self, ws: WebSocket) -> None:
        if ws in self.admin_connections:
            self.admin_connections.remove(ws)

    async def connect_client(self, client_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self.client_connections[client_id] = ws

    def disconnect_client(self, client_id: int) -> None:
        self.client_connections.pop(client_id, None)

    async def broadcast_admin(self, message: dict) -> None:
        dead = []
        for ws in self.admin_connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_admin(ws)

    async def send_to_client(self, client_id: int, message: dict) -> bool:
        ws = self.client_connections.get(client_id)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            self.disconnect_client(client_id)
            return False


manager = ConnectionManager()
