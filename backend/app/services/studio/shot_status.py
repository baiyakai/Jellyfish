"""镜头流程状态计算服务。"""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import Shot, ShotCandidateStatus, ShotExtractedCandidate, ShotStatus
from app.models.task import GenerationTask, GenerationTaskStatus
from app.models.task_links import GenerationTaskLink
from app.services.common import entity_not_found


_ACTIVE_GENERATION_STATUSES = (
    GenerationTaskStatus.pending,
    GenerationTaskStatus.running,
    GenerationTaskStatus.streaming,
)


def _active_task_stmt(shot_id: str) -> Select[tuple[int]]:
    return (
        select(func.count(GenerationTask.id))
        .select_from(GenerationTaskLink)
        .join(GenerationTask, GenerationTask.id == GenerationTaskLink.task_id)
        .where(GenerationTaskLink.relation_entity_id == shot_id)
        .where(GenerationTask.status.in_(_ACTIVE_GENERATION_STATUSES))
    )


async def has_active_generation_tasks(db: AsyncSession, *, shot_id: str) -> bool:
    """判断镜头是否仍有进行中的关键生成任务。"""
    count = await db.scalar(_active_task_stmt(shot_id))
    return bool(count)


async def _count_candidates(db: AsyncSession, *, shot_id: str) -> tuple[int, int]:
    """统计镜头候选项总数和未处理数量。

    这里显式走 SQL 计数，避免在异步场景下访问 relationship
    触发隐式懒加载。
    """
    total_stmt = select(func.count(ShotExtractedCandidate.id)).where(
        ShotExtractedCandidate.shot_id == shot_id
    )
    unresolved_stmt = (
        select(func.count(ShotExtractedCandidate.id))
        .where(ShotExtractedCandidate.shot_id == shot_id)
        .where(ShotExtractedCandidate.candidate_status == ShotCandidateStatus.pending)
    )
    total = int(await db.scalar(total_stmt) or 0)
    unresolved = int(await db.scalar(unresolved_stmt) or 0)
    return total, unresolved


async def recompute_shot_status(db: AsyncSession, *, shot_id: str) -> ShotStatus:
    """按镜头候选确认状态重新计算流程状态。"""
    shot = await db.get(Shot, shot_id)
    if shot is None:
        raise ValueError(entity_not_found("Shot"))

    if await has_active_generation_tasks(db, shot_id=shot_id):
        shot.status = ShotStatus.generating
        await db.flush()
        return shot.status

    if shot.skip_extraction:
        shot.status = ShotStatus.ready
        await db.flush()
        return shot.status

    if shot.last_extracted_at is None:
        shot.status = ShotStatus.pending
        await db.flush()
        return shot.status

    total_candidates, unresolved = await _count_candidates(db, shot_id=shot_id)
    if total_candidates == 0:
        shot.status = ShotStatus.ready
        await db.flush()
        return shot.status

    shot.status = ShotStatus.ready if unresolved == 0 else ShotStatus.pending
    await db.flush()
    return shot.status


async def mark_shot_generating(db: AsyncSession, *, shot_id: str) -> ShotStatus:
    """在生成类任务启动后，显式切镜头状态为 generating。"""
    shot = await db.get(Shot, shot_id)
    if shot is None:
        raise ValueError(entity_not_found("Shot"))
    shot.status = ShotStatus.generating
    await db.flush()
    return shot.status
