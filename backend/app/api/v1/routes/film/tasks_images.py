from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.task_manager import DeliveryMode, SqlAlchemyTaskStore, TaskManager
from app.dependencies import get_db, get_nothinking_llm
from app.models.task_links import GenerationTaskLink
from app.schemas.common import ApiResponse, created_response
from app.services.film.shot_frame_prompt_tasks import (
    build_run_args as build_shot_frame_prompt_run_args,
    normalize_frame_type,
    relation_type_for_frame,
    run_shot_frame_prompt_task,
)
from app.services.studio import mark_shot_generating

from .common import (
    ShotFramePromptRequest,
    TaskCreated,
    _CreateOnlyTask,
)
router = APIRouter()


@router.post(
    "/tasks/shot-frame-prompts",
    response_model=ApiResponse[TaskCreated],
    status_code=201,
    summary="镜头分镜帧提示词生成（任务版）",
)
async def create_shot_frame_prompt_task(
    body: ShotFramePromptRequest,
    llm: BaseChatModel = Depends(get_nothinking_llm),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    frame_type = normalize_frame_type(body.frame_type)
    relation_type = relation_type_for_frame(frame_type)

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    run_args = await build_shot_frame_prompt_run_args(
        db,
        shot_id=body.shot_id,
        frame_type=frame_type,
    )

    task_record = await tm.create(task=_CreateOnlyTask(), mode=DeliveryMode.async_polling, run_args=run_args)
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="prompt",
            relation_type=relation_type,
            relation_entity_id=body.shot_id,
        )
    )
    await mark_shot_generating(db, shot_id=body.shot_id)
    await db.commit()

    asyncio.create_task(run_shot_frame_prompt_task(task_id=task_record.id, run_args=run_args, llm=llm))
    return created_response(TaskCreated(task_id=task_record.id))
