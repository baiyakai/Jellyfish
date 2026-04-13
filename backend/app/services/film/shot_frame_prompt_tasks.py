from __future__ import annotations

import re

from fastapi import HTTPException
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
from app.models.studio import (
    Chapter,
    Character,
    Costume,
    ProjectCostumeLink,
    ProjectPropLink,
    ProjectSceneLink,
    Prop,
    Scene,
    Shot,
    ShotCharacterLink,
    ShotDetail,
)
from app.services.llm.runtime import build_default_text_llm_sync
from app.services.common import entity_not_found, invalid_choice
from app.services.studio.shot_status import recompute_shot_status
from app.services.worker.async_task_support import cancel_if_requested_async
from app.services.worker.task_logging import log_task_event, log_task_failure


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


def _enum_value(value: object | None) -> str:
    if value is None:
        return ""
    raw = getattr(value, "value", value)
    return str(raw or "")


def _compact_text(value: str | None) -> str:
    return str(value or "").strip()


def _join_context_lines(lines: list[str]) -> str:
    cleaned = [line for line in lines if line]
    return "\n".join(cleaned) if cleaned else "无"


def _build_character_context(characters: list[Character]) -> str:
    lines: list[str] = []
    for character in characters:
        fragments: list[str] = []
        if _compact_text(character.description):
            fragments.append(_compact_text(character.description))
        actor = getattr(character, "actor", None)
        if actor is not None and _compact_text(getattr(actor, "name", None)):
            actor_desc = f"演员形象：{_compact_text(getattr(actor, 'name', None))}"
            if _compact_text(getattr(actor, "description", None)):
                actor_desc += f"（{_compact_text(getattr(actor, 'description', None))}）"
            fragments.append(actor_desc)
        costume = getattr(character, "costume", None)
        if costume is not None and _compact_text(getattr(costume, "name", None)):
            costume_desc = f"默认服装：{_compact_text(getattr(costume, 'name', None))}"
            if _compact_text(getattr(costume, "description", None)):
                costume_desc += f"（{_compact_text(getattr(costume, 'description', None))}）"
            fragments.append(costume_desc)
        line = f"- {character.name}"
        if fragments:
            line += f"：{'；'.join(fragments)}"
        lines.append(line)
    return _join_context_lines(lines)


def _build_named_asset_context(assets: list[Scene] | list[Prop] | list[Costume]) -> str:
    lines: list[str] = []
    for asset in assets:
        line = f"- {asset.name}"
        if _compact_text(getattr(asset, "description", None)):
            line += f"：{_compact_text(getattr(asset, 'description', None))}"
        lines.append(line)
    return _join_context_lines(lines)


def _build_subject_priority(
    *,
    characters: list[Character],
    scenes: list[Scene],
    props: list[Prop],
    costumes: list[Costume],
) -> str:
    parts: list[str] = []
    if characters:
        primary_names = "、".join(character.name for character in characters[:2])
        parts.append(f"优先以角色 {primary_names} 作为画面主体")
        if len(characters) > 2:
            support_names = "、".join(character.name for character in characters[2:])
            parts.append(f"其余角色 {support_names} 仅在能强化画面关系时再补充")
    if scenes:
        parts.append(f"优先建立场景 {scenes[0].name} 的环境信息")
    if props:
        prop_names = "、".join(prop.name for prop in props[:2])
        parts.append(f"道具 {prop_names} 仅在进入主动作或构图焦点时重点写入")
    if costumes:
        costume_names = "、".join(costume.name for costume in costumes[:2])
        parts.append(f"服装 {costume_names} 主要用于强化人物外观一致性，不必喧宾夺主")
    return "；".join(parts) if parts else "优先根据镜头信息突出主角色和主场景，不必平均铺陈所有元素"


def _extract_context_names(context_text: str | None) -> list[str]:
    names: list[str] = []
    for raw_line in str(context_text or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        body = line[2:]
        name = body.split("：", 1)[0].strip()
        if name:
            names.append(name)
    return names


def _cleanup_generated_prompt(prompt: str) -> str:
    text = str(prompt or "").strip()
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned: list[str] = []
    after_generation_heading = False
    for line in lines:
        if line == "## 生成内容":
            after_generation_heading = True
            cleaned = []
            continue
        if line == "## 图片内容说明" or re.fullmatch(r"图\d+\s*[:：].*", line):
            continue
        cleaned.append(line)
    if after_generation_heading and cleaned:
        return "\n".join(cleaned).strip()
    return "\n".join(cleaned).strip()


def _validate_generated_prompt(prompt: str, input_dict: dict[str, object]) -> list[str]:
    issues: list[str] = []
    text = str(prompt or "").strip()
    if not text:
        return ["生成结果为空"]
    if "## 图片内容说明" in text or "## 生成内容" in text or re.search(r"(^|\n)\s*图\d+\s*[:：]", text):
        issues.append("结果混入了图片映射说明，应只保留基础提示词")
    primary_characters = _extract_context_names(str(input_dict.get("character_context") or ""))
    if primary_characters:
        lead_names = primary_characters[:2]
        if not any(name in text for name in lead_names):
            issues.append(f"结果缺少主角色名称：{'、'.join(lead_names)}")
    return issues


def _build_retry_guidance(issues: list[str]) -> str:
    if not issues:
        return ""
    return "请严格修正以下问题后重新生成：\n- " + "\n- ".join(issues)


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
            selectinload(Shot.detail).selectinload(ShotDetail.scene),
            selectinload(Shot.chapter).selectinload(Chapter.project),
            selectinload(Shot.character_links)
            .selectinload(ShotCharacterLink.character)
            .selectinload(Character.actor),
            selectinload(Shot.character_links)
            .selectinload(ShotCharacterLink.character)
            .selectinload(Character.costume),
            selectinload(Shot.scene_links).selectinload(ProjectSceneLink.scene),
            selectinload(Shot.prop_links).selectinload(ProjectPropLink.prop),
            selectinload(Shot.costume_links).selectinload(ProjectCostumeLink.costume),
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
    visual_style = _enum_value(getattr(project, "visual_style", None))
    style = _enum_value(getattr(project, "style", None))
    unify_style = bool(getattr(project, "unify_style", True)) if project is not None else True

    characters = [
        link.character
        for link in sorted(list(getattr(shot, "character_links", []) or []), key=lambda item: (item.index, item.id))
        if getattr(link, "character", None) is not None
    ]
    scenes_by_id: dict[str, Scene] = {}
    detail_scene = getattr(detail, "scene", None)
    if detail_scene is not None:
        scenes_by_id[str(detail_scene.id)] = detail_scene
    for link in list(getattr(shot, "scene_links", []) or []):
        scene = getattr(link, "scene", None)
        if scene is not None:
            scenes_by_id[str(scene.id)] = scene
    props = [
        link.prop
        for link in list(getattr(shot, "prop_links", []) or [])
        if getattr(link, "prop", None) is not None
    ]
    costumes = [
        link.costume
        for link in list(getattr(shot, "costume_links", []) or [])
        if getattr(link, "costume", None) is not None
    ]
    scenes = list(scenes_by_id.values())

    return {
        "shot_id": shot_id,
        "frame_type": normalized_frame_type,
        "input": {
            "script_excerpt": shot.script_excerpt or "",
            "title": shot.title or "",
            "visual_style": visual_style,
            "style": style,
            "unify_style": unify_style,
            "camera_shot": _enum_value(detail.camera_shot),
            "angle": _enum_value(detail.angle),
            "movement": _enum_value(detail.movement),
            "atmosphere": detail.atmosphere or "",
            "shot_description": detail.description or "",
            "mood_tags": detail.mood_tags or [],
            "vfx_type": _enum_value(detail.vfx_type),
            "vfx_note": detail.vfx_note or "",
            "duration": detail.duration,
            "scene_id": detail.scene_id,
            "dialog_summary": dialog_summary,
            "character_context": _build_character_context(characters),
            "scene_context": _build_named_asset_context(scenes),
            "prop_context": _build_named_asset_context(props),
            "costume_context": _build_named_asset_context(costumes),
            "subject_priority": _build_subject_priority(
                characters=characters,
                scenes=scenes,
                props=props,
                costumes=costumes,
            ),
        },
    }


async def run_shot_frame_prompt_task(
    task_id: str,
    run_args: dict,
) -> None:
    async with async_session_maker() as session:
        try:
            store = SqlAlchemyTaskStore(session)
            await store.set_status(task_id, TaskStatus.running)
            await store.set_progress(task_id, 10)
            await session.commit()
            log_task_event("shot_frame_prompt", task_id, "running")
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("shot_frame_prompt", task_id, "cancelled", stage="before_execute")
                return

            frame_type = str(run_args.get("frame_type") or "")
            shot_id = str(run_args.get("shot_id") or "")
            input_dict = dict(run_args.get("input") or {})
            llm = await session.run_sync(lambda sync_db: build_default_text_llm_sync(sync_db, thinking=False))

            if frame_type == "first":
                agent = ShotFirstFramePromptAgent(llm)
            elif frame_type == "last":
                agent = ShotLastFramePromptAgent(llm)
            else:
                agent = ShotKeyFramePromptAgent(llm)
            input_dict.setdefault("retry_guidance", "")
            result = await agent.aextract(**input_dict)
            quality_issues = _validate_generated_prompt(result.prompt, input_dict)
            if quality_issues:
                retry_input = dict(input_dict)
                retry_input["retry_guidance"] = _build_retry_guidance(quality_issues)
                retry_result = await agent.aextract(**retry_input)
                retry_issues = _validate_generated_prompt(retry_result.prompt, retry_input)
                if not retry_issues:
                    input_dict = retry_input
                    result = retry_result
                    quality_issues = []
                else:
                    result.prompt = _cleanup_generated_prompt(retry_result.prompt) or _cleanup_generated_prompt(result.prompt) or result.prompt
                    input_dict = retry_input
                    quality_issues = retry_issues
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("shot_frame_prompt", task_id, "cancelled", stage="after_execute")
                return

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

            result_payload = result.model_dump()
            result_payload["debug_context"] = dict(input_dict)
            result_payload["quality_checks"] = {
                "passed": not quality_issues,
                "issues": quality_issues,
            }
            await store.set_result(task_id, result_payload)
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("shot_frame_prompt", task_id, "cancelled", stage="after_persist")
                return
            await store.set_progress(task_id, 100)
            await store.set_status(task_id, TaskStatus.succeeded)
            await recompute_shot_status(session, shot_id=shot_id)
            await session.commit()
            log_task_event("shot_frame_prompt", task_id, "succeeded")
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
            log_task_failure("shot_frame_prompt", task_id, str(exc))
