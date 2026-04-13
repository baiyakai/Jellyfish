from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import (
    Actor,
    CameraAngle,
    CameraMovement,
    CameraShotType,
    Chapter,
    Character,
    Costume,
    DialogueLineMode,
    Project,
    ProjectCostumeLink,
    ProjectPropLink,
    ProjectSceneLink,
    ProjectStyle,
    ProjectVisualStyle,
    Prop,
    Scene,
    Shot,
    ShotCharacterLink,
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
        unify_style=True,
    )
    chapter = Chapter(id="c1", project_id="p1", index=1, title="第一章")
    shot = Shot(id="s1", chapter_id="c1", index=1, title="镜头一", script_excerpt="角色推门而入。")
    actor = Actor(
        id="actor-1",
        name="演员甲",
        description="短发、冷峻",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
    )
    costume = Costume(
        id="costume-1",
        name="黑色风衣",
        description="修身长款、利落",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
    )
    character = Character(
        id="char-1",
        project_id="p1",
        name="主角",
        description="克制、警惕，带着压迫感",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
        actor_id="actor-1",
        costume_id="costume-1",
    )
    scene = Scene(
        id="scene-1",
        name="废弃走廊",
        description="昏暗、潮湿、狭长",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
    )
    prop = Prop(
        id="prop-1",
        name="手电筒",
        description="金属外壳，冷白光束",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
    )
    detail = ShotDetail(
        id="s1",
        camera_shot=CameraShotType.ms,
        angle=CameraAngle.eye_level,
        movement=CameraMovement.static,
        scene_id="scene-1",
        duration=5,
        atmosphere="压抑",
        mood_tags=["紧张", "克制"],
        follow_atmosphere=True,
        vfx_type=VFXType.none,
        vfx_note="无",
        description="狭长走廊里，主角谨慎前行并回头确认身后动静。",
    )
    line = ShotDialogLine(
        shot_detail_id="s1",
        index=0,
        text="我们到了。",
        line_mode=DialogueLineMode.dialogue,
        speaker_name="主角",
    )
    shot_character_link = ShotCharacterLink(shot_id="s1", character_id="char-1", index=0)
    scene_link = ProjectSceneLink(project_id="p1", chapter_id="c1", shot_id="s1", scene_id="scene-1")
    prop_link = ProjectPropLink(project_id="p1", chapter_id="c1", shot_id="s1", prop_id="prop-1")
    costume_link = ProjectCostumeLink(project_id="p1", chapter_id="c1", shot_id="s1", costume_id="costume-1")
    db.add_all(
        [
            project,
            chapter,
            shot,
            actor,
            costume,
            character,
            scene,
            prop,
            detail,
            line,
            shot_character_link,
            scene_link,
            prop_link,
            costume_link,
        ]
    )
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
        assert run_args["input"]["unify_style"] is True
        assert run_args["input"]["shot_description"] == "狭长走廊里，主角谨慎前行并回头确认身后动静。"
        assert "主角：克制、警惕，带着压迫感" in run_args["input"]["character_context"]
        assert "演员形象：演员甲（短发、冷峻）" in run_args["input"]["character_context"]
        assert "默认服装：黑色风衣（修身长款、利落）" in run_args["input"]["character_context"]
        assert run_args["input"]["scene_context"] == "- 废弃走廊：昏暗、潮湿、狭长"
        assert run_args["input"]["prop_context"] == "- 手电筒：金属外壳，冷白光束"
        assert run_args["input"]["costume_context"] == "- 黑色风衣：修身长款、利落"
        assert "优先以角色 主角 作为画面主体" in run_args["input"]["subject_priority"]
        assert "优先建立场景 废弃走廊 的环境信息" in run_args["input"]["subject_priority"]
        assert "道具 手电筒 仅在进入主动作或构图焦点时重点写入" in run_args["input"]["subject_priority"]
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
