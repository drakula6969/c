from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..auth import check_admin_token
from ..database import get_db
from ..models import Client
from ..ws_manager import manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/admin")
async def ws_admin(websocket: WebSocket, token: str = Query(...)):
    if not check_admin_token(token):
        await websocket.close(code=4403)
        return

    await manager.connect_admin(websocket)
    try:
        while True:
            # Админ-панель просто держит соединение открытым и изредка
            # шлёт "ping" для keepalive; содержимое нам не важно.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_admin(websocket)


@router.websocket("/ws/client")
async def ws_client(websocket: WebSocket, token: str = Query(...), db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.token == token).first()
    if client is None:
        await websocket.close(code=4403)
        return

    await manager.connect_client(client.id, websocket)
    client.last_seen = datetime.now(timezone.utc)
    db.commit()
    await manager.broadcast_admin({"type": "status", "client_id": client.id, "online": True})

    try:
        while True:
            # Клиент может слать {"type":"ping"} вместо/вместе с REST-heartbeat.
            await websocket.receive_text()
            client.last_seen = datetime.now(timezone.utc)
            db.commit()
    except WebSocketDisconnect:
        manager.disconnect_client(client.id)
        await manager.broadcast_admin({"type": "status", "client_id": client.id, "online": False})
