import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import config
from ..auth import get_current_client, require_admin
from ..database import get_db
from ..models import Client
from ..schemas import ClientOut, OkResponse, RegisterRequest, RegisterResponse

router = APIRouter(tags=["clients"])


def _is_online(client: Client) -> bool:
    if client.last_seen is None:
        return False
    last_seen = client.last_seen
    # Страховка для старых строк в SQLite: там время могло сохраниться
    # без часового пояса. Считаем такое время UTC, а не локальным.
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - last_seen
    return delta.total_seconds() <= config.ONLINE_THRESHOLD_SECONDS


@router.post("/register", response_model=RegisterResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if not secrets.compare_digest(payload.enrollment_key, config.ENROLLMENT_KEY):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid enrollment key")

    existing = db.query(Client).filter(Client.hardware_id == payload.hardware_id).first()
    if existing is not None:
        # Повторный запуск той же флешки на этом же ПК — просто отдаём
        # существующие учётные данные, не плодим дубликаты.
        existing.last_seen = datetime.now(timezone.utc)
        db.commit()
        return RegisterResponse(client_id=existing.id, code=existing.code, token=existing.token)

    client = Client(
        code="PENDING",
        hardware_id=payload.hardware_id,
        name=payload.pc_name,
        token=secrets.token_urlsafe(32),
    )
    db.add(client)
    db.flush()  # получаем client.id, ещё не коммитя
    client.code = f"PC-{client.id:04d}"
    db.commit()
    db.refresh(client)

    return RegisterResponse(client_id=client.id, code=client.code, token=client.token)


@router.post("/me/heartbeat", response_model=OkResponse)
def heartbeat(client: Client = Depends(get_current_client), db: Session = Depends(get_db)):
    client.last_seen = datetime.now(timezone.utc)
    db.commit()
    return OkResponse()


@router.get("/admin/clients", response_model=list[ClientOut])
def list_clients(
    _: bool = Depends(require_admin), db: Session = Depends(get_db)
):
    clients = db.query(Client).order_by(Client.id.asc()).all()
    return [
        ClientOut(
            id=c.id,
            code=c.code,
            name=c.name,
            online=_is_online(c),
            last_seen=c.last_seen,
            registered_at=c.registered_at,
        )
        for c in clients
    ]
