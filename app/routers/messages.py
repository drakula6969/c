from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_current_client, require_admin
from ..database import get_db
from ..models import Client, Message
from ..schemas import MessageOut, SendMessageRequest
from ..ws_manager import manager

router = APIRouter(tags=["messages"])


@router.post("/admin/clients/{client_id}/messages", response_model=MessageOut)
async def send_message(
    client_id: int,
    payload: SendMessageRequest,
    _: bool = Depends(require_admin),
    db: Session = Depends(get_db),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    msg = Message(client_id=client_id, sender="admin", text=payload.text)
    db.add(msg)
    db.commit()
    db.refresh(msg)

    await manager.send_to_client(
        client_id,
        {
            "type": "reply",
            "message_id": msg.id,
            "text": msg.text,
            "created_at": msg.created_at.isoformat(),
        },
    )

    return MessageOut.model_validate(msg)


@router.get("/admin/clients/{client_id}/messages", response_model=list[MessageOut])
def list_messages(
    client_id: int, _: bool = Depends(require_admin), db: Session = Depends(get_db)
):
    msgs = (
        db.query(Message)
        .filter(Message.client_id == client_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return [MessageOut.model_validate(m) for m in msgs]


@router.get("/me/messages/latest", response_model=Optional[MessageOut])
def my_latest_message(
    client: Client = Depends(get_current_client), db: Session = Depends(get_db)
):
    """Используется кнопкой «Ответ» на клиенте: отдаёт последнее сообщение
    от администратора для этого компьютера (или null, если ответов ещё не было)."""
    msg = (
        db.query(Message)
        .filter(Message.client_id == client.id, Message.sender == "admin")
        .order_by(Message.created_at.desc())
        .first()
    )
    return MessageOut.model_validate(msg) if msg else None
