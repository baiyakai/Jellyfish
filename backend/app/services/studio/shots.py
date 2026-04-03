"""镜头服务：Shot 的分页查询与 CRUD。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import apply_keyword_filter, apply_order, paginate
from app.models.studio import Chapter, Shot
from app.schemas.common import ApiResponse, PaginatedData, paginated_response
from app.schemas.studio.shots import ShotCreate, ShotRead, ShotUpdate
from app.services.common import (
    create_and_refresh,
    delete_if_exists,
    entity_already_exists,
    entity_not_found,
    ensure_not_exists,
    flush_and_refresh,
    get_or_404,
    patch_model,
    require_entity,
)


async def list_paginated(
    db: AsyncSession,
    *,
    chapter_id: str | None,
    q: str | None,
    order: str | None,
    is_desc: bool,
    page: int,
    page_size: int,
    allow_fields: set[str],
) -> ApiResponse[PaginatedData[ShotRead]]:
    """分页查询镜头。"""
    stmt = select(Shot)
    if chapter_id is not None:
        stmt = stmt.where(Shot.chapter_id == chapter_id)
    stmt = apply_keyword_filter(stmt, q=q, fields=[Shot.title, Shot.script_excerpt])
    stmt = apply_order(
        stmt,
        model=Shot,
        order=order,
        is_desc=is_desc,
        allow_fields=allow_fields,
        default="index",
    )
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)
    return paginated_response(
        [ShotRead.model_validate(x) for x in items],
        page=page,
        page_size=page_size,
        total=total,
    )


async def create(
    db: AsyncSession,
    *,
    body: ShotCreate,
) -> Shot:
    """创建镜头。"""
    await ensure_not_exists(db, Shot, body.id, detail=entity_already_exists("Shot"))
    await require_entity(db, Chapter, body.chapter_id, detail=entity_not_found("Chapter"), status_code=400)
    return await create_and_refresh(db, Shot(**body.model_dump()))


async def get(
    db: AsyncSession,
    *,
    shot_id: str,
) -> Shot:
    """获取镜头。"""
    return await get_or_404(db, Shot, shot_id, detail=entity_not_found("Shot"))


async def update(
    db: AsyncSession,
    *,
    shot_id: str,
    body: ShotUpdate,
) -> Shot:
    """更新镜头。"""
    obj = await get_or_404(db, Shot, shot_id, detail=entity_not_found("Shot"))
    update_data = body.model_dump(exclude_unset=True)
    if "chapter_id" in update_data:
        await require_entity(
            db,
            Chapter,
            update_data["chapter_id"],
            detail=entity_not_found("Chapter"),
            status_code=400,
        )
    patch_model(obj, update_data)
    return await flush_and_refresh(db, obj)


async def delete(
    db: AsyncSession,
    *,
    shot_id: str,
) -> None:
    """删除镜头。"""
    await delete_if_exists(db, Shot, shot_id)
