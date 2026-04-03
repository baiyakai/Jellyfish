from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import (
    CameraAngle,
    CameraMovement,
    CameraShotType,
    Chapter,
    DialogueLineMode,
    Project,
    ProjectStyle,
    ProjectVisualStyle,
    Shot,
    ShotDetail,
    ShotDialogLine,
    VFXType,
)
from app.services.film.shot_frame_prompt_tasks import (
    build_run_args,
    normalize_frame_type,
    relation_type_for_frame,
)


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


async def _seed_shot_graph(db: AsyncSession) -> None:
    project = Project(
        id="p1",
        name="项目一",
        description="",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
    )
    chapter = Chapter(id="c1", project_id="p1", index=1, title="第一章")
    shot = Shot(id="s1", chapter_id="c1", index=1, title="镜头一", script_excerpt="角色推门而入。")
    detail = ShotDetail(
        id="s1",
        camera_shot=CameraShotType.ms,
        angle=CameraAngle.eye_level,
        movement=CameraMovement.static,
        duration=5,
        atmosphere="压抑",
        mood_tags=["紧张", "克制"],
        follow_atmosphere=True,
        vfx_type=VFXType.none,
        vfx_note="无",
    )
    line = ShotDialogLine(
        shot_detail_id="s1",
        index=0,
        text="我们到了。",
        line_mode=DialogueLineMode.dialogue,
        speaker_name="主角",
    )
    db.add_all([project, chapter, shot, detail, line])
    await db.commit()


def test_normalize_frame_type_and_relation_type() -> None:
    assert normalize_frame_type(" First ") == "first"
    assert relation_type_for_frame("first") == "shot_first_frame_prompt"
    assert relation_type_for_frame("last") == "shot_last_frame_prompt"
    assert relation_type_for_frame("key") == "shot_key_frame_prompt"

    with pytest.raises(HTTPException) as exc_info:
        normalize_frame_type("middle")

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_build_run_args_aggregates_dialog_and_project_style() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)

        run_args = await build_run_args(db, shot_id="s1", frame_type="first")

        assert run_args["frame_type"] == "first"
        assert run_args["shot_id"] == "s1"
        assert run_args["input"]["title"] == "镜头一"
        assert run_args["input"]["script_excerpt"] == "角色推门而入。"
        assert run_args["input"]["camera_shot"] == "MS"
        assert run_args["input"]["angle"] == "EYE_LEVEL"
        assert run_args["input"]["movement"] == "STATIC"
        assert run_args["input"]["dialog_summary"] == "我们到了。"
        assert run_args["input"]["visual_style"] == ProjectVisualStyle.live_action.value
        assert run_args["input"]["style"] == ProjectStyle.real_people_city.value
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_requires_shot_detail() -> None:
    db, engine = await _build_session()
    async with db:
        project = Project(
            id="p1",
            name="项目一",
            description="",
            style=ProjectStyle.real_people_city,
            visual_style=ProjectVisualStyle.live_action,
        )
        chapter = Chapter(id="c1", project_id="p1", index=1, title="第一章")
        shot = Shot(id="s1", chapter_id="c1", index=1, title="镜头一")
        db.add_all([project, chapter, shot])
        await db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await build_run_args(db, shot_id="s1", frame_type="key")

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "ShotDetail not found"
    await engine.dispose()
