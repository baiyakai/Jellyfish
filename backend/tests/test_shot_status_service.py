from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import (
    Chapter,
    Project,
    Prop,
    ProjectStyle,
    ProjectVisualStyle,
    Scene,
    Shot,
    ShotDetail,
    ShotCandidateStatus,
    ShotCandidateType,
    ShotDialogLine,
    ShotExtractedCandidate,
    ShotStatus,
)
from app.models.task import GenerationDeliveryMode, GenerationTask, GenerationTaskStatus
from app.models.task_links import GenerationTaskLink
from app.schemas.skills.script_processing import StudioScriptExtractionDraft, StudioShotDraft
from app.services.studio import (
    create_project_asset_link,
    delete_project_asset_link,
    get_shot_assets_overview,
    ignore_shot_extracted_candidate,
    link_shot_extracted_candidate,
    list_shot_extracted_candidates,
    replace_shot_extracted_candidates,
    set_skip_extraction,
    sync_shot_extracted_candidates_from_draft,
)
from app.services.studio.shot_details import update as update_shot_detail
from app.schemas.studio.shots import ProjectAssetLinkCreate, ShotDetailUpdate
from app.services.studio import mark_shot_generating, recompute_shot_status


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


async def _seed_graph(db: AsyncSession) -> Shot:
    project = Project(
        id="project-1",
        name="项目一",
        description="",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
    )
    chapter = Chapter(id="chapter-1", project_id="project-1", index=1, title="第一章")
    shot = Shot(id="shot-1", chapter_id="chapter-1", index=1, title="镜头一")
    db.add_all([project, chapter, shot])
    await db.flush()
    return shot


@pytest.mark.asyncio
async def test_recompute_shot_status_keeps_pending_without_candidates() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        status = await recompute_shot_status(db, shot_id=shot.id)
        assert status == ShotStatus.pending
        assert shot.status == ShotStatus.pending
    await engine.dispose()


@pytest.mark.asyncio
async def test_set_skip_extraction_marks_shot_ready() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        updated = await set_skip_extraction(db, shot_id=shot.id, skip=True)
        assert updated.skip_extraction is True
        assert updated.status == ShotStatus.ready
    await engine.dispose()


@pytest.mark.asyncio
async def test_replace_candidates_marks_pending_until_all_resolved() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        rows = await replace_shot_extracted_candidates(
            db,
            shot_id=shot.id,
            candidates=[
                {"candidate_type": "character", "candidate_name": "仙女A"},
                {"candidate_type": "scene", "candidate_name": "河边"},
            ],
        )

        assert len(rows) == 2
        assert shot.status == ShotStatus.pending

        await link_shot_extracted_candidate(db, candidate_id=rows[0].id, linked_entity_id="char-1")
        assert shot.status == ShotStatus.pending

        await ignore_shot_extracted_candidate(db, candidate_id=rows[1].id)
        assert shot.status == ShotStatus.ready
    await engine.dispose()


@pytest.mark.asyncio
async def test_shot_ready_does_not_depend_on_dialog_lines() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        detail = ShotDetail(
            id=shot.id,
            camera_shot="MS",
            angle="EYE_LEVEL",
            movement="STATIC",
            duration=3,
        )
        db.add(detail)
        await db.flush()

        rows = await replace_shot_extracted_candidates(
            db,
            shot_id=shot.id,
            candidates=[{"candidate_type": "scene", "candidate_name": "河边"}],
        )

        await ignore_shot_extracted_candidate(db, candidate_id=rows[0].id)
        status = await recompute_shot_status(db, shot_id=shot.id)
        dialog_rows = (
            await db.execute(select(ShotDialogLine).where(ShotDialogLine.shot_detail_id == shot.id))
        ).scalars().all()

        assert status == ShotStatus.ready
        assert shot.status == ShotStatus.ready
        assert len(dialog_rows) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_ignore_candidate_refreshes_updated_at_for_safe_response_serialization() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        rows = await replace_shot_extracted_candidates(
            db,
            shot_id=shot.id,
            candidates=[{"candidate_type": "prop", "candidate_name": "银斧头"}],
        )

        row = await ignore_shot_extracted_candidate(db, candidate_id=rows[0].id)

        # 这里直接读取 updated_at，确保不会在响应序列化阶段触发异步懒加载。
        assert row.updated_at is not None
        assert row.candidate_status == ShotCandidateStatus.ignored
    await engine.dispose()


@pytest.mark.asyncio
async def test_replace_candidates_replaces_old_rows() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        await replace_shot_extracted_candidates(
            db,
            shot_id=shot.id,
            candidates=[{"candidate_type": "character", "candidate_name": "旧角色"}],
        )
        rows = await replace_shot_extracted_candidates(
            db,
            shot_id=shot.id,
            candidates=[{"candidate_type": "prop", "candidate_name": "新道具"}],
        )

        assert len(rows) == 1
        assert rows[0].candidate_type == ShotCandidateType.prop
        assert rows[0].candidate_name == "新道具"
    await engine.dispose()


@pytest.mark.asyncio
async def test_replace_candidates_preserves_existing_linked_status_by_same_name() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        rows = await replace_shot_extracted_candidates(
            db,
            shot_id=shot.id,
            candidates=[
                {"candidate_type": "character", "candidate_name": "仙女A"},
                {"candidate_type": "scene", "candidate_name": "河边"},
            ],
        )

        await link_shot_extracted_candidate(db, candidate_id=rows[0].id, linked_entity_id="char-1")
        await ignore_shot_extracted_candidate(db, candidate_id=rows[1].id)
        assert shot.status == ShotStatus.ready

        new_rows = await replace_shot_extracted_candidates(
            db,
            shot_id=shot.id,
            candidates=[
                {"candidate_type": "character", "candidate_name": "仙女A"},
                {"candidate_type": "scene", "candidate_name": "河边"},
            ],
        )
        status_by_name = {row.candidate_name: row.candidate_status for row in new_rows}
        overview = await get_shot_assets_overview(db, shot_id=shot.id)

        assert status_by_name["仙女A"] == ShotCandidateStatus.linked
        assert status_by_name["河边"] == ShotCandidateStatus.pending
        assert shot.status == ShotStatus.pending
        assert overview.summary.pending_count == 1

        await ignore_shot_extracted_candidate(db, candidate_id=new_rows[1].id)
        overview_after_ignore = await get_shot_assets_overview(db, shot_id=shot.id)

        assert overview_after_ignore.summary.pending_count == 0
        assert shot.status == ShotStatus.ready
    await engine.dispose()


@pytest.mark.asyncio
async def test_sync_from_extraction_draft_marks_empty_extraction_as_ready() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        draft = StudioScriptExtractionDraft(
            project_id="project-1",
            chapter_id="chapter-1",
            script_text="测试文本",
            characters=[],
            scenes=[],
            props=[],
            costumes=[],
            shots=[
                StudioShotDraft(
                    index=1,
                    title="镜头一",
                    script_excerpt="摘录",
                    scene_name=None,
                    character_names=[],
                    prop_names=[],
                    costume_names=[],
                    dialogue_lines=[],
                    actions=[],
                )
            ],
        )

        await sync_shot_extracted_candidates_from_draft(db, chapter_id="chapter-1", draft=draft)

        assert shot.last_extracted_at is not None
        assert shot.status == ShotStatus.ready
    await engine.dispose()


@pytest.mark.asyncio
async def test_sync_from_extraction_draft_persists_candidate_description_in_payload() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        draft = StudioScriptExtractionDraft(
            project_id="project-1",
            chapter_id="chapter-1",
            script_text="测试文本",
            characters=[],
            scenes=[
                {
                    "name": "河边",
                    "description": "一条雾气弥漫的河岸，岸边有湿润石块",
                    "thumbnail": "/api/v1/studio/files/file-1/download",
                    "file_id": "file-1",
                }
            ],
            props=[],
            costumes=[],
            shots=[
                StudioShotDraft(
                    index=1,
                    title="镜头一",
                    script_excerpt="摘录",
                    scene_name="河边",
                    character_names=[],
                    prop_names=[],
                    costume_names=[],
                    dialogue_lines=[],
                    actions=[],
                )
            ],
        )

        await sync_shot_extracted_candidates_from_draft(db, chapter_id="chapter-1", draft=draft)
        rows = await list_shot_extracted_candidates(db, shot_id=shot.id)

        assert len(rows) == 1
        assert rows[0].candidate_name == "河边"
        assert rows[0].payload["description"] == "一条雾气弥漫的河岸，岸边有湿润石块"
        assert rows[0].payload["thumbnail"] == "/api/v1/studio/files/file-1/download"
        assert rows[0].payload["file_id"] == "file-1"
    await engine.dispose()


@pytest.mark.asyncio
async def test_recompute_shot_status_prefers_generating_when_active_task_exists() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        await replace_shot_extracted_candidates(
            db,
            shot_id=shot.id,
            candidates=[{"candidate_type": "character", "candidate_name": "仙女A"}],
        )
        candidate = (
            await db.get(ShotExtractedCandidate, 1)
        )
        assert candidate is not None
        candidate.candidate_status = ShotCandidateStatus.linked

        db.add(
            GenerationTask(
                id="task-1",
                mode=GenerationDeliveryMode.async_polling,
                status=GenerationTaskStatus.running,
                payload={},
            )
        )
        db.add(
            GenerationTaskLink(
                task_id="task-1",
                resource_type="video",
                relation_type="shot_video",
                relation_entity_id=shot.id,
            )
        )
        await db.flush()

        status = await recompute_shot_status(db, shot_id=shot.id)

        assert status == ShotStatus.generating
        assert shot.status == ShotStatus.generating
    await engine.dispose()


@pytest.mark.asyncio
async def test_mark_shot_generating_updates_status_directly() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        status = await mark_shot_generating(db, shot_id=shot.id)
        assert status == ShotStatus.generating
        assert shot.status == ShotStatus.generating
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_project_asset_link_marks_matching_prop_candidate_as_linked() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        db.add(
            Prop(
                id="prop-1",
                name="银斧头",
                description="",
                style=ProjectStyle.real_people_city,
                view_count=1,
                tags=[],
                visual_style=ProjectVisualStyle.live_action,
            )
        )
        await replace_shot_extracted_candidates(
            db,
            shot_id=shot.id,
            candidates=[{"candidate_type": "prop", "candidate_name": "银斧头"}],
        )

        await create_project_asset_link(
            db,
            entity_type="prop",
            body=ProjectAssetLinkCreate(
                project_id="project-1",
                chapter_id="chapter-1",
                shot_id=shot.id,
                asset_id="prop-1",
            ),
        )

        rows = await list_shot_extracted_candidates(db, shot_id=shot.id)
        assert len(rows) == 1
        assert rows[0].candidate_status == ShotCandidateStatus.linked
        assert rows[0].linked_entity_id == "prop-1"
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_project_asset_link_marks_matching_prop_candidate_back_to_pending() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        db.add(
            Prop(
                id="prop-1",
                name="银斧头",
                description="",
                style=ProjectStyle.real_people_city,
                view_count=1,
                tags=[],
                visual_style=ProjectVisualStyle.live_action,
            )
        )
        await replace_shot_extracted_candidates(
            db,
            shot_id=shot.id,
            candidates=[{"candidate_type": "prop", "candidate_name": "银斧头"}],
        )

        link = await create_project_asset_link(
            db,
            entity_type="prop",
            body=ProjectAssetLinkCreate(
                project_id="project-1",
                chapter_id="chapter-1",
                shot_id=shot.id,
                asset_id="prop-1",
            ),
        )
        await delete_project_asset_link(db, entity_type="prop", link_id=link.id)

        rows = await list_shot_extracted_candidates(db, shot_id=shot.id)
        assert len(rows) == 1
        assert rows[0].candidate_status == ShotCandidateStatus.pending
        assert rows[0].linked_entity_id is None
        assert rows[0].confirmed_at is None
        assert shot.status == ShotStatus.pending
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_shot_detail_scene_marks_matching_scene_candidate_as_linked() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        db.add(
            ShotDetail(
                id=shot.id,
                camera_shot="close_up",
                angle="eye_level",
                movement="static",
                duration=3,
                mood_tags=[],
                atmosphere="",
                follow_atmosphere=True,
                has_bgm=False,
                vfx_type="none",
                vfx_note="",
                first_frame_prompt="",
                last_frame_prompt="",
                key_frame_prompt="",
            )
        )
        db.add(
            Scene(
                id="scene-1",
                name="河边",
                description="",
                style=ProjectStyle.real_people_city,
                view_count=1,
                tags=[],
                visual_style=ProjectVisualStyle.live_action,
            )
        )
        await db.flush()
        await replace_shot_extracted_candidates(
            db,
            shot_id=shot.id,
            candidates=[{"candidate_type": "scene", "candidate_name": "河边"}],
        )

        await update_shot_detail(
            db,
            shot_id=shot.id,
            body=ShotDetailUpdate(scene_id="scene-1"),
        )

        rows = await list_shot_extracted_candidates(db, shot_id=shot.id)
        assert len(rows) == 1
        assert rows[0].candidate_status == ShotCandidateStatus.linked
        assert rows[0].linked_entity_id == "scene-1"
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_shot_detail_scene_change_marks_old_candidate_back_to_pending() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        db.add(
            ShotDetail(
                id=shot.id,
                camera_shot="close_up",
                angle="eye_level",
                movement="static",
                duration=3,
                mood_tags=[],
                atmosphere="",
                follow_atmosphere=True,
                has_bgm=False,
                vfx_type="none",
                vfx_note="",
                first_frame_prompt="",
                last_frame_prompt="",
                key_frame_prompt="",
            )
        )
        db.add_all(
            [
                Scene(
                    id="scene-1",
                    name="河边",
                    description="",
                    style=ProjectStyle.real_people_city,
                    view_count=1,
                    tags=[],
                    visual_style=ProjectVisualStyle.live_action,
                ),
                Scene(
                    id="scene-2",
                    name="山洞",
                    description="",
                    style=ProjectStyle.real_people_city,
                    view_count=1,
                    tags=[],
                    visual_style=ProjectVisualStyle.live_action,
                ),
            ]
        )
        await db.flush()
        await replace_shot_extracted_candidates(
            db,
            shot_id=shot.id,
            candidates=[
                {"candidate_type": "scene", "candidate_name": "河边"},
                {"candidate_type": "scene", "candidate_name": "山洞"},
            ],
        )

        await update_shot_detail(db, shot_id=shot.id, body=ShotDetailUpdate(scene_id="scene-1"))
        await update_shot_detail(db, shot_id=shot.id, body=ShotDetailUpdate(scene_id="scene-2"))

        rows = await list_shot_extracted_candidates(db, shot_id=shot.id)
        by_name = {row.candidate_name: row for row in rows}
        assert by_name["河边"].candidate_status == ShotCandidateStatus.pending
        assert by_name["河边"].linked_entity_id is None
        assert by_name["山洞"].candidate_status == ShotCandidateStatus.linked
        assert by_name["山洞"].linked_entity_id == "scene-2"
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_shot_detail_scene_clear_marks_old_candidate_back_to_pending() -> None:
    db, engine = await _build_session()
    async with db:
        shot = await _seed_graph(db)
        db.add(
            ShotDetail(
                id=shot.id,
                camera_shot="close_up",
                angle="eye_level",
                movement="static",
                duration=3,
                mood_tags=[],
                atmosphere="",
                follow_atmosphere=True,
                has_bgm=False,
                vfx_type="none",
                vfx_note="",
                first_frame_prompt="",
                last_frame_prompt="",
                key_frame_prompt="",
            )
        )
        db.add(
            Scene(
                id="scene-1",
                name="河边",
                description="",
                style=ProjectStyle.real_people_city,
                view_count=1,
                tags=[],
                visual_style=ProjectVisualStyle.live_action,
            )
        )
        await db.flush()
        await replace_shot_extracted_candidates(
            db,
            shot_id=shot.id,
            candidates=[{"candidate_type": "scene", "candidate_name": "河边"}],
        )

        await update_shot_detail(db, shot_id=shot.id, body=ShotDetailUpdate(scene_id="scene-1"))
        await update_shot_detail(db, shot_id=shot.id, body=ShotDetailUpdate(scene_id=None))

        rows = await list_shot_extracted_candidates(db, shot_id=shot.id)
        assert len(rows) == 1
        assert rows[0].candidate_status == ShotCandidateStatus.pending
        assert rows[0].linked_entity_id is None
        assert rows[0].confirmed_at is None
        assert shot.status == ShotStatus.pending
    await engine.dispose()
