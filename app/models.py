from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Хранит время в UTC и всегда возвращает timezone-aware datetime.

    SQLite не умеет хранить часовой пояс и возвращает naive datetime, из-за
    чего сравнение с datetime.now(timezone.utc) падало с TypeError. Для
    SQLite пишем naive UTC, а при чтении снова помечаем его как UTC; для
    PostgreSQL (TIMESTAMP WITH TIME ZONE) сохраняем aware-значение.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Client(Base):
    """Один зарегистрированный компьютер (один запуск программы с флешки)."""

    __tablename__ = "clients"

    id = Column(Integer, primary_key=True)
    code = Column(String(16), unique=True, index=True, nullable=False)  # "PC-0001"
    hardware_id = Column(String(128), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=True)
    token = Column(String(64), unique=True, index=True, nullable=False)

    registered_at = Column(UTCDateTime, default=utcnow, nullable=False)
    last_seen = Column(UTCDateTime, nullable=True)

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
    created_at = Column(UTCDateTime, default=utcnow, nullable=False)

    client = relationship("Client", back_populates="screenshots")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    sender = Column(String(16), nullable=False)  # "admin" | "client"
    text = Column(Text, nullable=False)
    created_at = Column(UTCDateTime, default=utcnow, nullable=False)

    client = relationship("Client", back_populates="messages")
