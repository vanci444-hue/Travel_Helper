"""行程仓储。本任务只提供查询，不写假行程。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Itinerary


class ItineraryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_ready_by_conversation(self, conversation_id: str) -> Itinerary | None:
        result = await self.db.execute(
            select(Itinerary).where(
                Itinerary.conversation_id == conversation_id,
                Itinerary.status == "ready",
            )
        )
        return result.scalar_one_or_none()

    async def list_by_conversation(self, conversation_id: str) -> list[Itinerary]:
        result = await self.db.execute(
            select(Itinerary).where(Itinerary.conversation_id == conversation_id)
        )
        return list(result.scalars().all())
