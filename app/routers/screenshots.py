from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from .. import config
from ..auth import get_current_client, require_admin
from ..schemas import ScreenshotOut
from ..store import Client, store
from ..ws_manager import manager

router = APIRouter(tags=["screenshots"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}


@router.post("/me/screenshots", response_model=ScreenshotOut)
async def upload_screenshot(
    file: UploadFile,
    client: Client = Depends(get_current_client),
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

    shot = store.add_screenshot(client_id=client.id, filename=filename, created_at=now)
    store.touch(client.id)

    await manager.broadcast_admin(
        {
            "type": "screenshot",
            "client_id": client.id,
            "screenshot_id": shot.id,
            "created_at": shot.created_at.isoformat(),
        }
    )

    return ScreenshotOut(id=shot.id, created_at=shot.created_at)


@router.get("/admin/clients/{client_id}/screenshots", response_model=list[ScreenshotOut])
def list_screenshots(client_id: int, _: bool = Depends(require_admin)):
    if store.get_client(client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return [
        ScreenshotOut(id=s.id, created_at=s.created_at)
        for s in store.list_screenshots(client_id)
    ]


@router.get("/admin/screenshots/{screenshot_id}/file")
def get_screenshot_file(screenshot_id: int, _: bool = Depends(require_admin)):
    shot = store.get_screenshot(screenshot_id)
    if shot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    client = store.get_client(shot.client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    path = (config.STORAGE_DIR / client.code / shot.filename).resolve()
    client_dir = (config.STORAGE_DIR / client.code).resolve()
    if path.parent != client_dir or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing on disk")
    media_type = "image/jpeg" if path.suffix.lower() == ".jpg" else "image/png"
    return FileResponse(path, media_type=media_type)


@router.delete("/admin/screenshots/{screenshot_id}")
def delete_screenshot(screenshot_id: int, _: bool = Depends(require_admin)):
    shot = store.get_screenshot(screenshot_id)
    if shot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screenshot not found")
    client = store.get_client(shot.client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    image_path = (config.STORAGE_DIR / client.code / shot.filename).resolve()
    client_dir = (config.STORAGE_DIR / client.code).resolve()
    if image_path.parent != client_dir:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid screenshot path")

    deleted = store.delete_screenshot(screenshot_id)
    if deleted is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screenshot not found")
    try:
        image_path.unlink(missing_ok=True)
    except OSError as exc:
        # Метаданные уже удалены, но сообщаем оператору, что файл остался.
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Screenshot record deleted, but image file could not be removed") from exc
    return {"status": "ok", "deleted_id": screenshot_id}
