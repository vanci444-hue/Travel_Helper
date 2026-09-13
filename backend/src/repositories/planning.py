"""规划任务仓储。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import PlanningJob


class PlanningRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, job: PlanningJob) -> PlanningJob:
        self.db.add(job)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ValueError(f"数据冲突: {exc.orig}") from exc
        await self.db.refresh(job)
        return job

    async def list_by_conversation(self, conversation_id: str) -> list[PlanningJob]:
        result = await self.db.execute(
            select(PlanningJob)
            .where(PlanningJob.conversation_id == conversation_id)
            .order_by(PlanningJob.started_at.desc())
        )
        return list(result.scalars().all())

    async def get_running(self, conversation_id: str) -> PlanningJob | None:
        result = await self.db.execute(
            select(PlanningJob).where(
                PlanningJob.conversation_id == conversation_id,
                PlanningJob.status == "running",
            )
        )
        return result.scalar_one_or_none()
