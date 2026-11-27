from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import get_current_client, require_admin
from ..schemas import MessageOut, SendMessageRequest
from ..store import Client, store
from ..ws_manager import manager

router = APIRouter(tags=["messages"])


def _to_out(msg) -> MessageOut:
    return MessageOut(id=msg.id, sender=msg.sender, text=msg.text, created_at=msg.created_at)


@router.post("/admin/clients/{client_id}/messages", response_model=MessageOut)
async def send_message(
    client_id: int,
    payload: SendMessageRequest,
    _: bool = Depends(require_admin),
):
    client = store.get_client(client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    msg = store.add_message(client_id=client_id, sender="admin", text=payload.text)

    await manager.send_to_client(
        client_id,
        {
            "type": "reply",
            "message_id": msg.id,
            "text": msg.text,
            "created_at": msg.created_at.isoformat(),
        },
    )

    return _to_out(msg)


@router.get("/admin/clients/{client_id}/messages", response_model=list[MessageOut])
def list_messages(client_id: int, _: bool = Depends(require_admin)):
    return [_to_out(m) for m in store.list_messages(client_id)]


@router.get("/me/messages/latest", response_model=Optional[MessageOut])
def my_latest_message(client: Client = Depends(get_current_client)):
    """Используется кнопкой «Ответ» на клиенте: отдаёт последнее сообщение
    от администратора для этого компьютера (или null, если ответов ещё не было)."""
    msg = store.latest_admin_message(client.id)
    return _to_out(msg) if msg else None
