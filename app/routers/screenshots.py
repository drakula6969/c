from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import config
from ..auth import get_current_client, require_admin
from ..database import get_db
from ..models import Client, Screenshot
from ..schemas import ScreenshotOut
from ..ws_manager import manager

router = APIRouter(tags=["screenshots"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}


@router.post("/me/screenshots", response_model=ScreenshotOut)
async def upload_screenshot(
    file: UploadFile,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only JPEG/PNG screenshots are accepted")

    data = await file.read()
    if len(data) > config.MAX_SCREENSHOT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Screenshot too large")

    ext = "jpg" if file.content_type == "image/jpeg" else "png"
    client_dir = config.STORAGE_DIR / client.code
    client_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    filename = f"{now.strftime('%Y%m%d_%H%M%S_%f')}.{ext}"
    (client_dir / filename).write_bytes(data)

    shot = Screenshot(client_id=client.id, filename=filename, created_at=now)
    db.add(shot)
    client.last_seen = now
    db.commit()
    db.refresh(shot)

    await manager.broadcast_admin(
        {
            "type": "screenshot",
            "client_id": client.id,
            "screenshot_id": shot.id,
            "created_at": shot.created_at.isoformat(),
        }
    )

    return ScreenshotOut.model_validate(shot)


@router.get("/admin/clients/{client_id}/screenshots", response_model=list[ScreenshotOut])
def list_screenshots(
    client_id: int, _: bool = Depends(require_admin), db: Session = Depends(get_db)
):
    shots = (
        db.query(Screenshot)
        .filter(Screenshot.client_id == client_id)
        .order_by(Screenshot.created_at.desc())
        .all()
    )
    return [ScreenshotOut.model_validate(s) for s in shots]


@router.get("/admin/screenshots/{screenshot_id}/file")
def get_screenshot_file(
    screenshot_id: int, _: bool = Depends(require_admin), db: Session = Depends(get_db)
):
    shot = db.query(Screenshot).filter(Screenshot.id == screenshot_id).first()
    if shot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    path = config.STORAGE_DIR / shot.client.code / shot.filename
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing on disk")
    media_type = "image/jpeg" if path.suffix == ".jpg" else "image/png"
    return FileResponse(path, media_type=media_type)
