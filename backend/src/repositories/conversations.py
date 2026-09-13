"""会话仓储。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Conversation
from src.models.common import utcnow


class ConversationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, conversation: Conversation) -> Conversation:
        self.db.add(conversation)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ValueError(f"数据冲突: {exc.orig}") from exc
        await self.db.refresh(conversation)
        return conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def list_page(self, *, offset: int, limit: int) -> tuple[list[Conversation], int]:
        total = await self.db.scalar(select(func.count()).select_from(Conversation))
        result = await self.db.execute(
            select(Conversation)
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def save(self, conversation: Conversation) -> Conversation:
        conversation.updated_at = utcnow()
        await self.db.flush()
        await self.db.refresh(conversation)
        return conversation
