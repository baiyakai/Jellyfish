"""Studio 实体与实体图片的通用服务。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import apply_keyword_filter, apply_order, paginate
from app.models.studio import (
    Actor,
    ActorImage,
    AssetViewAngle,
    Chapter,
    Character,
    CharacterImage,
    Costume,
    CostumeImage,
    Project,
    ProjectActorLink,
    ProjectCostumeLink,
    ProjectPropLink,
    ProjectSceneLink,
    Prop,
    PropImage,
    Scene,
    SceneImage,
    Shot,
    ShotCharacterLink,
)
from app.schemas.studio.assets import (
    AssetCreate,
    AssetImageCreate,
    AssetImageUpdate,
    AssetUpdate,
    CharacterImageRead,
    CostumeImageRead,
    PropImageRead,
    SceneImageRead,
)
from app.schemas.studio.cast import ActorCreate, ActorRead, ActorUpdate, CharacterCreate, CharacterRead, CharacterUpdate
from app.schemas.studio.cast_images import ActorImageRead
from app.utils.project_links import upsert_project_link

ENTITY_ORDER_FIELDS = {"name", "style", "visual_style", "created_at", "updated_at"}
IMAGE_ORDER_FIELDS = {"id", "quality_level", "view_angle", "created_at", "updated_at"}
DOWNLOAD_URL_TEMPLATE = "/api/v1/studio/files/{file_id}/download"
DEFAULT_VIEW_ANGLES: tuple[AssetViewAngle, ...] = (
    AssetViewAngle.front,
    AssetViewAngle.left,
    AssetViewAngle.right,
    AssetViewAngle.back,
)

_LINK_MODEL_BY_ENTITY: dict[str, tuple[type, str]] = {
    "actor": (ProjectActorLink, "actor_id"),
    "scene": (ProjectSceneLink, "scene_id"),
    "prop": (ProjectPropLink, "prop_id"),
    "costume": (ProjectCostumeLink, "costume_id"),
}


@dataclass(frozen=True)
class EntitySpec:
    model: type
    image_model: type
    id_field: str
    read_model: type | None
    create_model: type
    update_model: type
    image_read_model: type
    image_create_model: type
    image_update_model: type


def download_url(file_id: str) -> str:
    return DOWNLOAD_URL_TEMPLATE.format(file_id=file_id)


async def resolve_thumbnails(
    db: AsyncSession,
    *,
    image_model: type,
    parent_field_name: str,
    parent_ids: list[str],
) -> dict[str, str]:
    if not parent_ids:
        return {}
    parent_field = getattr(image_model, parent_field_name)
    stmt = select(image_model).where(parent_field.in_(parent_ids), image_model.file_id.is_not(None))
    rows = (await db.execute(stmt)).scalars().all()
    best: dict[str, tuple[int, int, int, str]] = {}
    for row in rows:
        file_id = row.file_id
        if not file_id:
            continue
        parent_id = getattr(row, parent_field_name)
        created_ts = int(row.created_at.timestamp()) if row.created_at else -1
        score = (1 if row.view_angle == AssetViewAngle.front else 0, created_ts, row.id)
        current = best.get(parent_id)
        if current is None or score > current[:3]:
            best[parent_id] = (*score, file_id)
    return {parent_id: download_url(score[3]) for parent_id, score in best.items()}


async def resolve_thumbnail_infos(
    db: AsyncSession,
    *,
    image_model: type,
    parent_field_name: str,
    parent_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """解析每个 parent_id 的最佳缩略图信息（thumbnail + image_id）。

    评分规则与 `resolve_thumbnails` 保持一致：
    - 优先 view_angle=front
    - 其次 created_at 新的优先
    - 其次 image 行 id 大的优先
    """

    if not parent_ids:
        return {}
    parent_field = getattr(image_model, parent_field_name)
    stmt = select(image_model).where(parent_field.in_(parent_ids), image_model.file_id.is_not(None))
    rows = (await db.execute(stmt)).scalars().all()
    best: dict[str, tuple[int, int, int, int, str]] = {}
    for row in rows:
        file_id = row.file_id
        if not file_id:
            continue
        parent_id = getattr(row, parent_field_name)
        created_ts = int(row.created_at.timestamp()) if row.created_at else -1
        image_id = int(row.id)
        score3 = (1 if row.view_angle == AssetViewAngle.front else 0, created_ts, image_id)
        current = best.get(parent_id)
        if current is None or score3 > current[:3]:
            best[parent_id] = (*score3, image_id, file_id)

    return {
        parent_id: {
            "image_id": info[3],
            "file_id": info[4],
            "thumbnail": download_url(info[4]),
        }
        for parent_id, info in best.items()
    }


def normalize_entity_type(entity_type: str) -> str:
    t = entity_type.strip().lower()
    if t not in {"actor", "character", "scene", "prop", "costume"}:
        raise HTTPException(status_code=400, detail="entity_type must be one of: actor/character/scene/prop/costume")
    return t


def entity_spec(entity_type: str) -> EntitySpec:
    t = normalize_entity_type(entity_type)
    if t == "actor":
        return EntitySpec(
            model=Actor,
            image_model=ActorImage,
            id_field="actor_id",
            read_model=ActorRead,
            create_model=ActorCreate,
            update_model=ActorUpdate,
            image_read_model=ActorImageRead,
            image_create_model=AssetImageCreate,
            image_update_model=AssetImageUpdate,
        )
    if t == "character":
        return EntitySpec(
            model=Character,
            image_model=CharacterImage,
            id_field="character_id",
            read_model=CharacterRead,
            create_model=CharacterCreate,
            update_model=CharacterUpdate,
            image_read_model=CharacterImageRead,
            image_create_model=AssetImageCreate,
            image_update_model=AssetImageUpdate,
        )
    if t == "scene":
        return EntitySpec(
            model=Scene,
            image_model=SceneImage,
            id_field="scene_id",
            read_model=None,
            create_model=AssetCreate,
            update_model=AssetUpdate,
            image_read_model=SceneImageRead,
            image_create_model=AssetImageCreate,
            image_update_model=AssetImageUpdate,
        )
    if t == "prop":
        return EntitySpec(
            model=Prop,
            image_model=PropImage,
            id_field="prop_id",
            read_model=None,
            create_model=AssetCreate,
            update_model=AssetUpdate,
            image_read_model=PropImageRead,
            image_create_model=AssetImageCreate,
            image_update_model=AssetImageUpdate,
        )
    return EntitySpec(
        model=Costume,
        image_model=CostumeImage,
        id_field="costume_id",
        read_model=None,
        create_model=AssetCreate,
        update_model=AssetUpdate,
        image_read_model=CostumeImageRead,
        image_create_model=AssetImageCreate,
        image_update_model=AssetImageUpdate,
    )


class StudioEntitiesService:
    """封装 studio 通用实体与图片的数据库操作。"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def check_names_existence(
        self,
        *,
        project_id: str,
        shot_id: str | None = None,
        character_names: list[str],
        prop_names: list[str],
        scene_names: list[str],
        costume_names: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """批量检测名称是否存在（模糊匹配），并标记是否已关联到项目。

        约定：
        - character：仅在该 project_id 下查找（Character.project_id）。
        - prop/scene/costume：exists 在全局资产表中查找；linked_to_project 通过 Project*Link 关联表判断。
        - linked_to_shot：仅当传入 shot_id 时检测；角色查 ShotCharacterLink，其余查 Project*Link（shot_id 精确匹配）。
        - 匹配规则：包含匹配（case-insensitive）：name ILIKE %q%
        """
        effective_shot_id = shot_id.strip() if shot_id and str(shot_id).strip() else None
        if effective_shot_id:
            shot_ok = (
                await self._db.execute(
                    select(Shot.id)
                    .join(Chapter, Shot.chapter_id == Chapter.id)
                    .where(Shot.id == effective_shot_id, Chapter.project_id == project_id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if shot_ok is None:
                raise HTTPException(status_code=404, detail="Shot not found or not in this project")

        async def _exists_in_character(q: str) -> bool:
            stmt = (
                select(Character.id)
                .where(Character.project_id == project_id, Character.name.ilike(f"%{q}%"))
                .limit(1)
            )
            return (await self._db.execute(stmt)).scalar_one_or_none() is not None

        async def _find_character_id(q: str) -> str | None:
            stmt = (
                select(Character.id)
                .where(Character.project_id == project_id, Character.name.ilike(f"%{q}%"))
                .limit(1)
            )
            row = (await self._db.execute(stmt)).scalar_one_or_none()
            return str(row) if row is not None else None

        async def _exists_in_asset(model: type, q: str) -> bool:
            stmt = select(getattr(model, "id")).where(getattr(model, "name").ilike(f"%{q}%")).limit(1)
            return (await self._db.execute(stmt)).scalar_one_or_none() is not None

        async def _find_asset_id(model: type, q: str) -> str | None:
            stmt = select(getattr(model, "id")).where(getattr(model, "name").ilike(f"%{q}%")).limit(1)
            row = (await self._db.execute(stmt)).scalar_one_or_none()
            return str(row) if row is not None else None

        async def _linked_prop(q: str) -> bool:
            stmt = (
                select(ProjectPropLink.id)
                .join(Prop, Prop.id == ProjectPropLink.prop_id)
                .where(ProjectPropLink.project_id == project_id, Prop.name.ilike(f"%{q}%"))
                .limit(1)
            )
            return (await self._db.execute(stmt)).scalar_one_or_none() is not None

        async def _find_linked_prop(q: str) -> tuple[int, str] | None:
            stmt = (
                select(ProjectPropLink.id, Prop.id)
                .join(Prop, Prop.id == ProjectPropLink.prop_id)
                .where(ProjectPropLink.project_id == project_id, Prop.name.ilike(f"%{q}%"))
                .limit(1)
            )
            row = (await self._db.execute(stmt)).first()
            if not row:
                return None
            link_id, prop_id = row
            return int(link_id), str(prop_id)

        async def _linked_scene(q: str) -> bool:
            stmt = (
                select(ProjectSceneLink.id)
                .join(Scene, Scene.id == ProjectSceneLink.scene_id)
                .where(ProjectSceneLink.project_id == project_id, Scene.name.ilike(f"%{q}%"))
                .limit(1)
            )
            return (await self._db.execute(stmt)).scalar_one_or_none() is not None

        async def _find_linked_scene(q: str) -> tuple[int, str] | None:
            stmt = (
                select(ProjectSceneLink.id, Scene.id)
                .join(Scene, Scene.id == ProjectSceneLink.scene_id)
                .where(ProjectSceneLink.project_id == project_id, Scene.name.ilike(f"%{q}%"))
                .limit(1)
            )
            row = (await self._db.execute(stmt)).first()
            if not row:
                return None
            link_id, scene_id = row
            return int(link_id), str(scene_id)

        async def _linked_costume(q: str) -> bool:
            stmt = (
                select(ProjectCostumeLink.id)
                .join(Costume, Costume.id == ProjectCostumeLink.costume_id)
                .where(ProjectCostumeLink.project_id == project_id, Costume.name.ilike(f"%{q}%"))
                .limit(1)
            )
            return (await self._db.execute(stmt)).scalar_one_or_none() is not None

        async def _find_linked_costume(q: str) -> tuple[int, str] | None:
            stmt = (
                select(ProjectCostumeLink.id, Costume.id)
                .join(Costume, Costume.id == ProjectCostumeLink.costume_id)
                .where(ProjectCostumeLink.project_id == project_id, Costume.name.ilike(f"%{q}%"))
                .limit(1)
            )
            row = (await self._db.execute(stmt)).first()
            if not row:
                return None
            link_id, costume_id = row
            return int(link_id), str(costume_id)

        characters_out: list[dict[str, Any]] = []
        for name in character_names or []:
            raw = str(name)
            q = raw.strip()
            if not q:
                characters_out.append(
                    {
                        "name": raw,
                        "exists": False,
                        "linked_to_project": False,
                        "linked_to_shot": False,
                        "asset_id": None,
                        "link_id": None,
                    }
                )
                continue
            char_id = await _find_character_id(q)
            exists = char_id is not None
            characters_out.append(
                {
                    "name": raw,
                    "exists": exists,
                    "linked_to_project": exists,
                    "linked_to_shot": False,
                    "asset_id": char_id,
                    "link_id": None,
                }
            )

        props_out: list[dict[str, Any]] = []
        for name in prop_names or []:
            raw = str(name)
            q = raw.strip()
            if not q:
                props_out.append(
                    {
                        "name": raw,
                        "exists": False,
                        "linked_to_project": False,
                        "linked_to_shot": False,
                        "asset_id": None,
                        "link_id": None,
                    }
                )
                continue
            linked_row = await _find_linked_prop(q)
            if linked_row is not None:
                link_id, prop_id = linked_row
                props_out.append(
                    {
                        "name": raw,
                        "exists": True,
                        "linked_to_project": True,
                        "linked_to_shot": False,
                        "asset_id": prop_id,
                        "link_id": link_id,
                    }
                )
                continue
            prop_id = await _find_asset_id(Prop, q)
            exists = prop_id is not None
            props_out.append(
                {
                    "name": raw,
                    "exists": exists,
                    "linked_to_project": False,
                    "linked_to_shot": False,
                    "asset_id": prop_id,
                    "link_id": None,
                }
            )

        scenes_out: list[dict[str, Any]] = []
        for name in scene_names or []:
            raw = str(name)
            q = raw.strip()
            if not q:
                scenes_out.append(
                    {
                        "name": raw,
                        "exists": False,
                        "linked_to_project": False,
                        "linked_to_shot": False,
                        "asset_id": None,
                        "link_id": None,
                    }
                )
                continue
            linked_row = await _find_linked_scene(q)
            if linked_row is not None:
                link_id, scene_id = linked_row
                scenes_out.append(
                    {
                        "name": raw,
                        "exists": True,
                        "linked_to_project": True,
                        "linked_to_shot": False,
                        "asset_id": scene_id,
                        "link_id": link_id,
                    }
                )
                continue
            scene_id = await _find_asset_id(Scene, q)
            exists = scene_id is not None
            scenes_out.append(
                {
                    "name": raw,
                    "exists": exists,
                    "linked_to_project": False,
                    "linked_to_shot": False,
                    "asset_id": scene_id,
                    "link_id": None,
                }
            )

        costumes_out: list[dict[str, Any]] = []
        for name in costume_names or []:
            raw = str(name)
            q = raw.strip()
            if not q:
                costumes_out.append(
                    {
                        "name": raw,
                        "exists": False,
                        "linked_to_project": False,
                        "linked_to_shot": False,
                        "asset_id": None,
                        "link_id": None,
                    }
                )
                continue
            linked_row = await _find_linked_costume(q)
            if linked_row is not None:
                link_id, costume_id = linked_row
                costumes_out.append(
                    {
                        "name": raw,
                        "exists": True,
                        "linked_to_project": True,
                        "linked_to_shot": False,
                        "asset_id": costume_id,
                        "link_id": link_id,
                    }
                )
                continue
            costume_id = await _find_asset_id(Costume, q)
            exists = costume_id is not None
            costumes_out.append(
                {
                    "name": raw,
                    "exists": exists,
                    "linked_to_project": False,
                    "linked_to_shot": False,
                    "asset_id": costume_id,
                    "link_id": None,
                }
            )

        if effective_shot_id:
            char_ids = {r["asset_id"] for r in characters_out if r.get("asset_id")}
            linked_char_ids: set[str] = set()
            if char_ids:
                stmt = select(ShotCharacterLink.character_id).where(
                    ShotCharacterLink.shot_id == effective_shot_id,
                    ShotCharacterLink.character_id.in_(char_ids),
                )
                linked_char_ids = {row[0] for row in (await self._db.execute(stmt)).all()}
            for r in characters_out:
                aid = r.get("asset_id")
                if aid and aid in linked_char_ids:
                    r["linked_to_shot"] = True

            prop_ids = {r["asset_id"] for r in props_out if r.get("asset_id")}
            linked_prop_ids: set[str] = set()
            if prop_ids:
                stmt = select(ProjectPropLink.prop_id).where(
                    ProjectPropLink.project_id == project_id,
                    ProjectPropLink.shot_id == effective_shot_id,
                    ProjectPropLink.prop_id.in_(prop_ids),
                )
                linked_prop_ids = {row[0] for row in (await self._db.execute(stmt)).all()}
            for r in props_out:
                aid = r.get("asset_id")
                if aid and aid in linked_prop_ids:
                    r["linked_to_shot"] = True

            scene_ids = {r["asset_id"] for r in scenes_out if r.get("asset_id")}
            linked_scene_ids: set[str] = set()
            if scene_ids:
                stmt = select(ProjectSceneLink.scene_id).where(
                    ProjectSceneLink.project_id == project_id,
                    ProjectSceneLink.shot_id == effective_shot_id,
                    ProjectSceneLink.scene_id.in_(scene_ids),
                )
                linked_scene_ids = {row[0] for row in (await self._db.execute(stmt)).all()}
            for r in scenes_out:
                aid = r.get("asset_id")
                if aid and aid in linked_scene_ids:
                    r["linked_to_shot"] = True

            costume_ids = {r["asset_id"] for r in costumes_out if r.get("asset_id")}
            linked_costume_ids: set[str] = set()
            if costume_ids:
                stmt = select(ProjectCostumeLink.costume_id).where(
                    ProjectCostumeLink.project_id == project_id,
                    ProjectCostumeLink.shot_id == effective_shot_id,
                    ProjectCostumeLink.costume_id.in_(costume_ids),
                )
                linked_costume_ids = {row[0] for row in (await self._db.execute(stmt)).all()}
            for r in costumes_out:
                aid = r.get("asset_id")
                if aid and aid in linked_costume_ids:
                    r["linked_to_shot"] = True

        return {
            "characters": characters_out,
            "props": props_out,
            "scenes": scenes_out,
            "costumes": costumes_out,
        }

    async def _resolve_thumbnails(self, *, image_model: type, parent_field_name: str, parent_ids: list[str]) -> dict[str, str]:
        return await resolve_thumbnails(
            self._db,
            image_model=image_model,
            parent_field_name=parent_field_name,
            parent_ids=parent_ids,
        )

    def _asset_read_payload(self, obj: Any, thumbnail: str) -> dict[str, Any]:
        return {
            "id": obj.id,
            "name": obj.name,
            "description": obj.description,
            "tags": obj.tags or [],
            "prompt_template_id": obj.prompt_template_id,
            "view_count": obj.view_count,
            "style": obj.style,
            "visual_style": obj.visual_style,
            "thumbnail": thumbnail,
        }

    async def list_entities(
        self,
        *,
        entity_type: str,
        q: str | None,
        style: str | None,
        visual_style: str | None,
        order: str | None,
        is_desc: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        t = normalize_entity_type(entity_type)
        spec = entity_spec(t)
        stmt = select(spec.model)
        stmt = apply_keyword_filter(stmt, q=q, fields=[spec.model.name, spec.model.description])
        if style:
            stmt = stmt.where(getattr(spec.model, "style") == style)
        if visual_style:
            stmt = stmt.where(getattr(spec.model, "visual_style") == visual_style)
        stmt = apply_order(stmt, model=spec.model, order=order, is_desc=is_desc, allow_fields=ENTITY_ORDER_FIELDS, default="created_at")
        items, total = await paginate(self._db, stmt=stmt, page=page, page_size=page_size)

        thumbnails = await self._resolve_thumbnails(
            image_model=spec.image_model,
            parent_field_name=spec.id_field,
            parent_ids=[x.id for x in items],
        )
        payload: list[dict[str, Any]] = []
        for x in items:
            thumbnail = thumbnails.get(x.id, "")
            if t in {"actor", "character"}:
                read_model = spec.read_model
                payload.append(read_model.model_validate(x).model_copy(update={"thumbnail": thumbnail}).model_dump())
            else:
                payload.append(self._asset_read_payload(x, thumbnail))
        return payload, total

    async def create_entity(self, *, entity_type: str, body: dict[str, Any]) -> dict[str, Any]:
        t = normalize_entity_type(entity_type)
        spec = entity_spec(t)
        parsed = spec.create_model.model_validate(body)
        data = parsed.model_dump()

        link_project_id: str | None = None
        link_chapter_id: str | None = None
        link_shot_id: str | None = None
        if t in _LINK_MODEL_BY_ENTITY:
            link_project_id = data.pop("project_id", None)
            link_chapter_id = data.pop("chapter_id", None)
            link_shot_id = data.pop("shot_id", None)

        exists = await self._db.get(spec.model, data["id"])
        if exists is not None:
            raise HTTPException(status_code=400, detail=f"{spec.model.__name__} with id={data['id']} already exists")

        if t == "character":
            if await self._db.get(Project, data["project_id"]) is None:
                raise HTTPException(status_code=400, detail="Project not found")
            if data.get("actor_id"):
                if await self._db.get(Actor, data["actor_id"]) is None:
                    raise HTTPException(status_code=400, detail="Actor not found")
            if data.get("costume_id") and await self._db.get(Costume, data["costume_id"]) is None:
                raise HTTPException(status_code=400, detail="Costume not found")

        obj = spec.model(**data)
        self._db.add(obj)
        await self._db.flush()
        await self._db.refresh(obj)

        if t in {"actor", "scene", "prop", "costume"}:
            count = int(getattr(obj, "view_count", 1) or 1)
            angles = list(DEFAULT_VIEW_ANGLES[: min(max(count, 0), len(DEFAULT_VIEW_ANGLES))])
            for angle in angles:
                self._db.add(spec.image_model(**{spec.id_field: obj.id, "view_angle": angle}))
            if angles:
                await self._db.flush()

        if link_project_id is not None and t in _LINK_MODEL_BY_ENTITY:
            link_model, asset_field = _LINK_MODEL_BY_ENTITY[t]
            await upsert_project_link(
                self._db,
                model=link_model,
                asset_field=asset_field,  # type: ignore[arg-type]
                asset_id=obj.id,
                project_id=link_project_id,
                chapter_id=link_chapter_id,
                shot_id=link_shot_id,
            )

        if t in {"actor", "character"}:
            read_model = spec.read_model
            payload = read_model.model_validate(obj).model_dump()
            payload["thumbnail"] = ""
            return payload
        return self._asset_read_payload(obj, "")

    async def get_entity(self, *, entity_type: str, entity_id: str) -> dict[str, Any]:
        t = normalize_entity_type(entity_type)
        spec = entity_spec(t)
        obj = await self._db.get(spec.model, entity_id)
        if obj is None:
            raise HTTPException(status_code=404, detail=f"{spec.model.__name__} not found")

        thumbnails = await self._resolve_thumbnails(
            image_model=spec.image_model,
            parent_field_name=spec.id_field,
            parent_ids=[entity_id],
        )
        thumbnail = thumbnails.get(entity_id, "")
        if t in {"actor", "character"}:
            read_model = spec.read_model
            return read_model.model_validate(obj).model_copy(update={"thumbnail": thumbnail}).model_dump()
        return self._asset_read_payload(obj, thumbnail)

    async def update_entity(self, *, entity_type: str, entity_id: str, body: dict[str, Any]) -> dict[str, Any]:
        t = normalize_entity_type(entity_type)
        spec = entity_spec(t)
        obj = await self._db.get(spec.model, entity_id)
        if obj is None:
            raise HTTPException(status_code=404, detail=f"{spec.model.__name__} not found")

        update_data = spec.update_model.model_validate(body).model_dump(exclude_unset=True)
        if t == "character":
            if "project_id" in update_data and await self._db.get(Project, update_data["project_id"]) is None:
                raise HTTPException(status_code=400, detail="Project not found")
            if "actor_id" in update_data and update_data["actor_id"] is not None and await self._db.get(Actor, update_data["actor_id"]) is None:
                raise HTTPException(status_code=400, detail="Actor not found")
            if "costume_id" in update_data and update_data["costume_id"] is not None and await self._db.get(Costume, update_data["costume_id"]) is None:
                raise HTTPException(status_code=400, detail="Costume not found")

        for k, v in update_data.items():
            setattr(obj, k, v)
        await self._db.flush()
        await self._db.refresh(obj)

        if t in {"actor", "character"}:
            read_model = spec.read_model
            payload = read_model.model_validate(obj).model_dump()
            payload["thumbnail"] = ""
            return payload
        return self._asset_read_payload(obj, "")

    async def delete_entity(self, *, entity_type: str, entity_id: str) -> None:
        spec = entity_spec(entity_type)
        obj = await self._db.get(spec.model, entity_id)
        if obj is None:
            return
        await self._db.delete(obj)
        await self._db.flush()

    async def list_entity_images(
        self,
        *,
        entity_type: str,
        entity_id: str,
        order: str | None,
        is_desc: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        spec = entity_spec(entity_type)
        parent = await self._db.get(spec.model, entity_id)
        if parent is None:
            raise HTTPException(status_code=404, detail=f"{spec.model.__name__} not found")

        id_field = getattr(spec.image_model, spec.id_field)
        stmt = select(spec.image_model).where(id_field == entity_id)
        stmt = apply_order(
            stmt,
            model=spec.image_model,
            order=order,
            is_desc=is_desc,
            allow_fields=IMAGE_ORDER_FIELDS,
            default="id",
        )
        items, total = await paginate(self._db, stmt=stmt, page=page, page_size=page_size)
        payload = [spec.image_read_model.model_validate(x).model_dump() for x in items]
        return payload, total

    async def create_entity_image(self, *, entity_type: str, entity_id: str, body: dict[str, Any]) -> dict[str, Any]:
        t = normalize_entity_type(entity_type)
        spec = entity_spec(t)
        parent = await self._db.get(spec.model, entity_id)
        if parent is None:
            raise HTTPException(status_code=404, detail=f"{spec.model.__name__} not found")

        parsed = spec.image_create_model.model_validate(body).model_dump()
        obj = spec.image_model(**{spec.id_field: entity_id, **parsed})
        self._db.add(obj)
        await self._db.flush()
        await self._db.refresh(obj)

        if t == "character" and getattr(obj, "is_primary", False):
            stmt = (
                CharacterImage.__table__.update()
                .where(CharacterImage.character_id == entity_id, CharacterImage.id != obj.id)
                .values(is_primary=False)
            )
            await self._db.execute(stmt)
            await self._db.refresh(obj)

        return spec.image_read_model.model_validate(obj).model_dump()

    async def update_entity_image(
        self,
        *,
        entity_type: str,
        entity_id: str,
        image_id: int,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        t = normalize_entity_type(entity_type)
        spec = entity_spec(t)
        obj = await self._db.get(spec.image_model, image_id)
        if obj is None or getattr(obj, spec.id_field) != entity_id:
            raise HTTPException(status_code=404, detail=f"{spec.image_model.__name__} not found")

        update_data = spec.image_update_model.model_validate(body).model_dump(exclude_unset=True)
        for k, v in update_data.items():
            setattr(obj, k, v)
        await self._db.flush()
        await self._db.refresh(obj)

        if t == "character" and update_data.get("is_primary") is True:
            stmt = (
                CharacterImage.__table__.update()
                .where(CharacterImage.character_id == entity_id, CharacterImage.id != obj.id)
                .values(is_primary=False)
            )
            await self._db.execute(stmt)
            await self._db.refresh(obj)

        return spec.image_read_model.model_validate(obj).model_dump()

    async def delete_entity_image(self, *, entity_type: str, entity_id: str, image_id: int) -> None:
        spec = entity_spec(entity_type)
        obj = await self._db.get(spec.image_model, image_id)
        if obj is None or getattr(obj, spec.id_field) != entity_id:
            return
        await self._db.delete(obj)
        await self._db.flush()
