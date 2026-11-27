from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Client(Base):
    """Один зарегистрированный компьютер (один запуск программы с флешки)."""

    __tablename__ = "clients"

    id = Column(Integer, primary_key=True)
    code = Column(String(16), unique=True, index=True, nullable=False)  # "PC-0001"
    hardware_id = Column(String(128), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=True)
    token = Column(String(64), unique=True, index=True, nullable=False)

    registered_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen = Column(DateTime(timezone=True), nullable=True)

    screenshots = relationship(
        "Screenshot", back_populates="client", cascade="all, delete-orphan"
    )
    messages = relationship(
        "Message", back_populates="client", cascade="all, delete-orphan"
    )


class Screenshot(Base):
    __tablename__ = "screenshots"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    filename = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    client = relationship("Client", back_populates="screenshots")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    sender = Column(String(16), nullable=False)  # "admin" | "client"
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    client = relationship("Client", back_populates="messages")
