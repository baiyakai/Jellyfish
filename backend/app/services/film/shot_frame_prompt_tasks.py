from __future__ import annotations

from fastapi import HTTPException
from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.chains.agents import (
    ShotFirstFramePromptAgent,
    ShotKeyFramePromptAgent,
    ShotLastFramePromptAgent,
)
from app.core.db import async_session_maker
from app.core.task_manager import SqlAlchemyTaskStore
from app.core.task_manager.types import TaskStatus
from app.models.studio import Chapter, Shot, ShotDetail
from app.services.common import entity_not_found, invalid_choice
from app.services.studio import recompute_shot_status


def normalize_frame_type(frame_type: str) -> str:
    value = (frame_type or "").strip().lower()
    if value not in {"first", "last", "key"}:
        raise HTTPException(status_code=400, detail=invalid_choice("frame_type", ["first", "last", "key"]))
    return value


def relation_type_for_frame(frame_type: str) -> str:
    if frame_type == "first":
        return "shot_first_frame_prompt"
    if frame_type == "last":
        return "shot_last_frame_prompt"
    return "shot_key_frame_prompt"


async def build_run_args(
    db: AsyncSession,
    *,
    shot_id: str,
    frame_type: str,
) -> dict:
    normalized_frame_type = normalize_frame_type(frame_type)
    shot_stmt = (
        select(Shot)
        .options(
            selectinload(Shot.detail).selectinload(ShotDetail.dialog_lines),
            selectinload(Shot.chapter).selectinload(Chapter.project),
        )
        .where(Shot.id == shot_id)
    )
    shot = (await db.execute(shot_stmt)).scalar_one_or_none()
    if shot is None:
        raise HTTPException(status_code=404, detail=entity_not_found("Shot"))
    if shot.detail is None:
        raise HTTPException(status_code=404, detail=entity_not_found("ShotDetail"))

    detail = shot.detail
    dialog_summary = "\n".join(line.text for line in (detail.dialog_lines or []) if line.text)
    project = getattr(getattr(shot, "chapter", None), "project", None)
    visual_style = str(getattr(project, "visual_style", "") or "")
    style = str(getattr(project, "style", "") or "")

    return {
        "shot_id": shot_id,
        "frame_type": normalized_frame_type,
        "input": {
            "script_excerpt": shot.script_excerpt or "",
            "title": shot.title or "",
            "camera_shot": detail.camera_shot.value if hasattr(detail.camera_shot, "value") else str(detail.camera_shot),
            "angle": detail.angle.value if hasattr(detail.angle, "value") else str(detail.angle),
            "movement": detail.movement.value if hasattr(detail.movement, "value") else str(detail.movement),
            "atmosphere": detail.atmosphere or "",
            "mood_tags": detail.mood_tags or [],
            "vfx_type": detail.vfx_type.value if hasattr(detail.vfx_type, "value") else str(detail.vfx_type),
            "vfx_note": detail.vfx_note or "",
            "duration": detail.duration,
            "scene_id": detail.scene_id,
            "dialog_summary": dialog_summary,
            "visual_style": visual_style,
            "style": style,
        },
    }


async def run_shot_frame_prompt_task(
    *,
    task_id: str,
    run_args: dict,
    llm: BaseChatModel,
) -> None:
    async with async_session_maker() as session:
        try:
            store = SqlAlchemyTaskStore(session)
            await store.set_status(task_id, TaskStatus.running)
            await store.set_progress(task_id, 10)
            await session.commit()

            frame_type = str(run_args.get("frame_type") or "")
            shot_id = str(run_args.get("shot_id") or "")
            input_dict = dict(run_args.get("input") or {})

            if frame_type == "first":
                agent = ShotFirstFramePromptAgent(llm)
            elif frame_type == "last":
                agent = ShotLastFramePromptAgent(llm)
            else:
                agent = ShotKeyFramePromptAgent(llm)
            result = await agent.aextract(**input_dict)

            if not shot_id:
                raise RuntimeError("Missing shot_id in run args")
            shot_detail = await session.get(ShotDetail, shot_id)
            if shot_detail is None:
                raise RuntimeError("ShotDetail not found when persisting prompt")

            if frame_type == "first":
                shot_detail.first_frame_prompt = result.prompt
            elif frame_type == "last":
                shot_detail.last_frame_prompt = result.prompt
            else:
                shot_detail.key_frame_prompt = result.prompt

            await store.set_result(task_id, result.model_dump())
            await store.set_progress(task_id, 100)
            await store.set_status(task_id, TaskStatus.succeeded)
            await recompute_shot_status(session, shot_id=shot_id)
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            async with async_session_maker() as s2:
                store = SqlAlchemyTaskStore(s2)
                await store.set_error(task_id, str(exc))
                await store.set_status(task_id, TaskStatus.failed)
                shot_id = str(run_args.get("shot_id") or "")
                if shot_id:
                    await recompute_shot_status(s2, shot_id=shot_id)
                await s2.commit()
