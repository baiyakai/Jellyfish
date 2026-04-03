from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.studio import (
    Actor,
    ActorImage,
    AssetViewAngle,
    Character,
    CharacterImage,
    Chapter,
    Costume,
    CostumeImage,
    PromptCategory,
    Prop,
    PropImage,
    Scene,
    SceneImage,
    Shot,
    ShotCharacterLink,
    ShotDetail,
    ShotFrameType,
)
from app.services.studio.image_task_references import (
    pick_front_ref_file_id,
    pick_ordered_ref_file_ids,
)
from app.services.common import entity_not_found, invalid_choice, not_belong_to, required_field
from app.services.studio.image_tasks import (
    asset_prompt_category,
    build_prompt_with_template,
    is_front_view,
    map_view_angle_for_prompt,
    shot_frame_prompt_category,
)


async def build_actor_prompt_and_refs(
    db: AsyncSession,
    *,
    actor_id: str,
    image_id: int | None,
) -> tuple[str, list[str], ActorImage]:
    actor = await db.get(Actor, actor_id)
    if actor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Actor"))
    if image_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=required_field("image_id", when="actor generation"),
        )
    image_row = await db.get(ActorImage, image_id)
    if image_row is None or image_row.actor_id != actor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=not_belong_to("image_id", "actor_id"),
        )
    front_view = is_front_view(image_row.view_angle)
    category = asset_prompt_category(relation_type="actor_image", is_front_view=front_view)
    prompt = await build_prompt_with_template(
        db,
        category=category,
        variables={
            "name": actor.name,
            "description": actor.description,
            "tags": ", ".join(actor.tags or []),
            "visual_style": actor.visual_style.value if hasattr(actor.visual_style, "value") else str(actor.visual_style),
            "style": actor.style.value if hasattr(actor.style, "value") else str(actor.style),
            "view_angle": map_view_angle_for_prompt(image_row.view_angle),
            "quality_level": image_row.quality_level,
            "format": image_row.format,
        },
        fallback_prompt=actor.description,
        not_found_msg="Actor.description is empty",
    )
    if front_view:
        return prompt, [], image_row
    fid = await pick_front_ref_file_id(
        db,
        image_model=ActorImage,
        parent_field_name="actor_id",
        parent_id=actor_id,
        preferred_quality_level=image_row.quality_level,
    )
    return prompt, ([fid] if fid else []), image_row


async def build_asset_prompt_and_refs(
    db: AsyncSession,
    *,
    asset_type: str,
    asset_id: str,
    image_id: int | None,
) -> tuple[str, list[str], str]:
    if image_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=required_field("image_id", when="asset image generation"),
        )

    asset_type_norm = asset_type.strip().lower()
    if asset_type_norm == "prop":
        asset = await db.get(Prop, asset_id)
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Prop"))
        image_row = await db.get(PropImage, image_id)
        if image_row is None or image_row.prop_id != asset_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=not_belong_to("image_id", "prop_id"),
            )
        relation_type = "prop_image"
        front_view = is_front_view(image_row.view_angle)
        category = asset_prompt_category(relation_type=relation_type, is_front_view=front_view)
        prompt = await build_prompt_with_template(
            db,
            category=category,
            variables={
                "name": asset.name,
                "description": asset.description,
                "tags": ", ".join(asset.tags or []),
                "visual_style": asset.visual_style.value if hasattr(asset.visual_style, "value") else str(asset.visual_style),
                "style": asset.style.value if hasattr(asset.style, "value") else str(asset.style),
                "view_angle": map_view_angle_for_prompt(image_row.view_angle),
                "quality_level": image_row.quality_level,
                "format": image_row.format,
            },
            fallback_prompt=asset.description,
            not_found_msg="Prop.description is empty",
        )
        if front_view:
            return prompt, [], relation_type
        fid = await pick_front_ref_file_id(
            db,
            image_model=PropImage,
            parent_field_name="prop_id",
            parent_id=asset_id,
            preferred_quality_level=image_row.quality_level,
        )
        return prompt, ([fid] if fid else []), relation_type
    if asset_type_norm == "scene":
        asset = await db.get(Scene, asset_id)
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Scene"))
        image_row = await db.get(SceneImage, image_id)
        if image_row is None or image_row.scene_id != asset_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=not_belong_to("image_id", "scene_id"),
            )
        relation_type = "scene_image"
        front_view = is_front_view(image_row.view_angle)
        category = asset_prompt_category(relation_type=relation_type, is_front_view=front_view)
        prompt = await build_prompt_with_template(
            db,
            category=category,
            variables={
                "name": asset.name,
                "description": asset.description,
                "tags": ", ".join(asset.tags or []),
                "visual_style": asset.visual_style.value if hasattr(asset.visual_style, "value") else str(asset.visual_style),
                "style": asset.style.value if hasattr(asset.style, "value") else str(asset.style),
                "view_angle": map_view_angle_for_prompt(image_row.view_angle),
                "quality_level": image_row.quality_level,
                "format": image_row.format,
            },
            fallback_prompt=asset.description,
            not_found_msg="Scene.description is empty",
        )
        if front_view:
            return prompt, [], relation_type
        fid = await pick_front_ref_file_id(
            db,
            image_model=SceneImage,
            parent_field_name="scene_id",
            parent_id=asset_id,
            preferred_quality_level=image_row.quality_level,
        )
        return prompt, ([fid] if fid else []), relation_type
    if asset_type_norm == "costume":
        asset = await db.get(Costume, asset_id)
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Costume"))
        image_row = await db.get(CostumeImage, image_id)
        if image_row is None or image_row.costume_id != asset_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=not_belong_to("image_id", "costume_id"),
            )
        relation_type = "costume_image"
        front_view = is_front_view(image_row.view_angle)
        category = asset_prompt_category(relation_type=relation_type, is_front_view=front_view)
        prompt = await build_prompt_with_template(
            db,
            category=category,
            variables={
                "name": asset.name,
                "description": asset.description,
                "tags": ", ".join(asset.tags or []),
                "visual_style": asset.visual_style.value if hasattr(asset.visual_style, "value") else str(asset.visual_style),
                "style": asset.style.value if hasattr(asset.style, "value") else str(asset.style),
                "view_angle": map_view_angle_for_prompt(image_row.view_angle),
                "quality_level": image_row.quality_level,
                "format": image_row.format,
            },
            fallback_prompt=asset.description,
            not_found_msg="Costume.description is empty",
        )
        if front_view:
            return prompt, [], relation_type
        fid = await pick_front_ref_file_id(
            db,
            image_model=CostumeImage,
            parent_field_name="costume_id",
            parent_id=asset_id,
            preferred_quality_level=image_row.quality_level,
        )
        return prompt, ([fid] if fid else []), relation_type
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=invalid_choice("asset_type", ["prop", "scene", "costume"]),
    )


async def build_character_prompt_and_refs(
    db: AsyncSession,
    *,
    character_id: str,
    image_id: int | None,
) -> tuple[str, list[str], CharacterImage]:
    character = await db.get(Character, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Character"))
    if image_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=required_field("image_id", when="character image generation"),
        )
    image_row = await db.get(CharacterImage, image_id)
    if image_row is None or image_row.character_id != character_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=not_belong_to("image_id", "character_id"),
        )
    prompt = await build_prompt_with_template(
        db,
        category=PromptCategory.combined,
        variables={
            "name": character.name,
            "description": character.description,
            "visual_style": character.visual_style.value if hasattr(character.visual_style, "value") else str(character.visual_style),
            "style": character.style.value if hasattr(character.style, "value") else str(character.style),
            "view_angle": map_view_angle_for_prompt(image_row.view_angle),
            "quality_level": image_row.quality_level,
            "format": image_row.format,
        },
        fallback_prompt=character.description,
        not_found_msg="Character.description is empty",
    )
    actor: Actor | None = await db.get(Actor, character.actor_id) if character.actor_id else None
    costume: Costume | None = await db.get(Costume, character.costume_id) if character.costume_id else None

    default_view_angles: tuple[AssetViewAngle, ...] = (
        AssetViewAngle.front,
        AssetViewAngle.left,
        AssetViewAngle.right,
        AssetViewAngle.back,
    )
    actor_refs: list[str] = []
    if actor is not None:
        actor_refs = await pick_ordered_ref_file_ids(
            db,
            image_model=ActorImage,
            parent_field_name="actor_id",
            parent_id=actor.id,
            view_angles=default_view_angles,
        )
    costume_refs: list[str] = []
    if costume is not None:
        costume_refs = await pick_ordered_ref_file_ids(
            db,
            image_model=CostumeImage,
            parent_field_name="costume_id",
            parent_id=costume.id,
            view_angles=default_view_angles,
        )
    return prompt, [*actor_refs, *costume_refs], image_row


def _cn_num(n: int) -> str:
    ones = {0: "零", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九"}
    if n <= 9:
        return ones[n]
    if n == 10:
        return "十"
    if n < 20:
        return f"十{ones[n - 10]}"
    tens = n // 10
    rem = n % 10
    if rem == 0:
        return f"{ones[tens]}十"
    return f"{ones[tens]}十{ones[rem]}"


async def build_shot_frame_prompt_and_refs(
    db: AsyncSession,
    *,
    shot_id: str,
    frame_type: ShotFrameType,
) -> tuple[str, list[str], ShotDetail]:
    shot_stmt = (
        select(ShotDetail)
        .options(selectinload(ShotDetail.shot).selectinload(Shot.chapter).selectinload(Chapter.project))
        .where(ShotDetail.id == shot_id)
    )
    shot_detail = (await db.execute(shot_stmt)).scalar_one_or_none()
    if shot_detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("ShotDetail"))

    project = getattr(getattr(getattr(shot_detail, "shot", None), "chapter", None), "project", None)
    visual_style_raw = getattr(project, "visual_style", None)
    visual_style = (
        visual_style_raw.value if visual_style_raw is not None and hasattr(visual_style_raw, "value") else str(visual_style_raw or "")
    )
    style_raw = getattr(project, "style", None)
    style = style_raw.value if style_raw is not None and hasattr(style_raw, "value") else str(style_raw or "")

    if frame_type == ShotFrameType.first:
        raw_prompt = (shot_detail.first_frame_prompt or "").strip()
    elif frame_type == ShotFrameType.last:
        raw_prompt = (shot_detail.last_frame_prompt or "").strip()
    else:
        raw_prompt = (shot_detail.key_frame_prompt or "").strip()
    if not raw_prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ShotDetail has no prompt for frame_type={frame_type}",
        )

    role_links_stmt = (
        select(ShotCharacterLink)
        .options(selectinload(ShotCharacterLink.character))
        .where(ShotCharacterLink.shot_id == shot_id)
        .order_by(ShotCharacterLink.index.asc())
    )
    role_links = (await db.execute(role_links_stmt)).scalars().all()

    role_names: list[str] = []
    role_image_ids: list[str] = []
    for link in role_links:
        character = link.character
        if character is None:
            continue
        fid = await pick_front_ref_file_id(
            db,
            image_model=CharacterImage,
            parent_field_name="character_id",
            parent_id=character.id,
            preferred_quality_level=None,
        )
        if fid is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CharacterImage front ref not found for character_id={character.id}, name={character.name}",
            )
        role_names.append(character.name)
        role_image_ids.append(fid)

    if role_links and not role_names:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid shot character image refs found",
        )
    if len(set(role_names)) != len(role_names):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate character names in shot character links; cannot map names to image order",
        )

    name_to_token: dict[str, str] = {name: f"图{_cn_num(i + 1)}" for i, name in enumerate(role_names)}
    sorted_pairs = sorted(name_to_token.items(), key=lambda kv: len(kv[0]), reverse=True)

    def _replace_names(text: str) -> str:
        out = text or ""
        for name, token in sorted_pairs:
            if name:
                out = out.replace(name, token)
        return out

    replaced_first = _replace_names(shot_detail.first_frame_prompt or "")
    replaced_last = _replace_names(shot_detail.last_frame_prompt or "")
    replaced_key = _replace_names(shot_detail.key_frame_prompt or "")
    base_prompt = _replace_names(raw_prompt)
    prompt = await build_prompt_with_template(
        db,
        category=shot_frame_prompt_category(frame_type),
        variables={
            "description": shot_detail.description,
            "atmosphere": shot_detail.atmosphere,
            "mood_tags": ", ".join(shot_detail.mood_tags or []),
            "visual_style": visual_style,
            "style": style,
            "camera_shot": shot_detail.camera_shot,
            "angle": shot_detail.angle,
            "movement": shot_detail.movement,
            "frame_type": frame_type,
            "first_frame_prompt": replaced_first,
            "last_frame_prompt": replaced_last,
            "key_frame_prompt": replaced_key,
            "base_prompt": base_prompt,
        },
        fallback_prompt=base_prompt,
        not_found_msg=f"ShotDetail has no prompt for frame_type={frame_type}",
    )
    return prompt, role_image_ids, shot_detail
