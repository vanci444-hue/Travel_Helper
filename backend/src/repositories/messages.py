"""消息仓储。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Message


class MessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, message: Message) -> Message:
        self.db.add(message)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ValueError(f"数据冲突: {exc.orig}") from exc
        await self.db.refresh(message)
        return message

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return list(result.scalars().all())
