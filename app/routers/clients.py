import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from .. import config
from ..auth import get_current_client, require_admin
from ..schemas import ClientOut, OkResponse, RegisterRequest, RegisterResponse
from ..store import Client, store

router = APIRouter(tags=["clients"])


def _is_online(client: Client) -> bool:
    if client.last_seen is None:
        return False
    delta = datetime.now(timezone.utc) - client.last_seen
    return delta.total_seconds() <= config.ONLINE_THRESHOLD_SECONDS


@router.post("/register", response_model=RegisterResponse)
def register(payload: RegisterRequest):
    if not secrets.compare_digest(payload.enrollment_key, config.ENROLLMENT_KEY):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid enrollment key")

    # Повторный запуск той же флешки на этом же ПК — store.register вернёт
    # существующие учётные данные, не плодя дубликаты.
    client = store.register(
        hardware_id=payload.hardware_id,
        name=payload.pc_name,
        token=secrets.token_urlsafe(32),
    )
    return RegisterResponse(client_id=client.id, code=client.code, token=client.token)


@router.post("/me/heartbeat", response_model=OkResponse)
def heartbeat(client: Client = Depends(get_current_client)):
    store.touch(client.id)
    return OkResponse()


@router.get("/admin/clients", response_model=list[ClientOut])
def list_clients(_: bool = Depends(require_admin)):
    return [
        ClientOut(
            id=c.id,
            code=c.code,
            name=c.name,
            online=_is_online(c),
            last_seen=c.last_seen,
            registered_at=c.registered_at,
        )
        for c in store.list_clients()
    ]
