from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .database import Base, engine
from .routers import clients, messages, screenshots, ws

app = FastAPI(title="PortableStream Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


app.include_router(clients.router, prefix="/api")
app.include_router(screenshots.router, prefix="/api")
app.include_router(messages.router, prefix="/api")
app.include_router(ws.router)

ADMIN_STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "admin"
app.mount("/admin", StaticFiles(directory=str(ADMIN_STATIC_DIR), html=True), name="admin")


@app.get("/")
def root():
    return {"service": "PortableStream Server", "admin_panel": "/admin"}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
