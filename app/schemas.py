from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    enrollment_key: str
    hardware_id: str = Field(..., min_length=4, max_length=128)
    pc_name: Optional[str] = Field(None, max_length=128)


class RegisterResponse(BaseModel):
    client_id: int
    code: str
    token: str


class ClientOut(BaseModel):
    id: int
    code: str
    name: Optional[str]
    online: bool
    last_seen: Optional[datetime]
    registered_at: datetime


class ScreenshotOut(BaseModel):
    id: int
    created_at: datetime


class MessageOut(BaseModel):
    id: int
    sender: str
    text: str
    created_at: datetime


class SendMessageResponse(MessageOut):
    # True means the active client WebSocket accepted the push. False means
    # the message is stored and the client will fetch it through REST polling.
    delivered: bool


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class OkResponse(BaseModel):
    status: str = "ok"
