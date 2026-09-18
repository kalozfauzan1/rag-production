"""Kontrak payload untuk endpoint chat."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Body request POST /api/chat/stream."""

    message: str = Field(min_length=1, max_length=4000)


class TokenData(BaseModel):
    """Payload event `token`: sepotong teks jawaban."""

    text: str


class DoneData(BaseModel):
    """Payload event `done`: akhir stream yang sukses."""

    finish_reason: str
