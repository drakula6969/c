import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .models import Client


def _extract_bearer(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token"
        )
    return authorization.split(" ", 1)[1].strip()


def require_admin(authorization: str = Header(None)) -> bool:
    token = _extract_bearer(authorization)
    if not secrets.compare_digest(token, config.ADMIN_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key"
        )
    return True


def get_current_client(
    authorization: str = Header(None), db: Session = Depends(get_db)
) -> Client:
    token = _extract_bearer(authorization)
    client = db.query(Client).filter(Client.token == token).first()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid client token"
        )
    return client


def check_admin_token(token: str) -> bool:
    """Та же проверка, что require_admin, но для WebSocket (токен из query)."""
    return bool(token) and secrets.compare_digest(token, config.ADMIN_API_KEY)
