from __future__ import annotations

from app.schemas.studio.shots import RenderedShotFramePromptRead, ShotFramePromptMappingRead
from app.services.studio.generation.frame.build_base import FrameBaseDraft
from app.services.studio.generation.frame.build_context import FrameGenerationContext
from app.services.studio.generation.shared.types import GenerationDerivedPreview


def replace_reference_names_in_prompt(
    *,
    base_prompt: str,
    mappings: list[ShotFramePromptMappingRead],
) -> str:
    """将提示词中的实体名称替换为稳定的图片 token。"""
    text = (base_prompt or "").strip()
    replace_pairs = [
        ((mapping.name or "").strip(), mapping.token)
        for mapping in mappings
        if (mapping.name or "").strip()
    ]
    replace_pairs.sort(key=lambda item: len(item[0]), reverse=True)
    for name, token in replace_pairs:
        text = text.replace(name, token)
    return text


def compose_shot_frame_rendered_prompt(
    *,
    replaced_prompt: str,
    mappings: list[ShotFramePromptMappingRead],
) -> str:
    """拼装最终提交给模型的关键帧提示词。"""
    lines: list[str] = []
    if mappings:
        lines.append("## 图片内容说明")
        for mapping in mappings:
            lines.append(f"{mapping.token}: {mapping.name}")
        lines.append("")
    lines.append("## 生成内容")
    lines.append((replaced_prompt or "").strip())
    return "\n".join(lines).strip()


class FrameDerivedPreview(GenerationDerivedPreview):
    """分镜帧图片生成的最终预览结果。"""

    kind: str = "frame"
    shot_id: str
    frame_type: str
    base_prompt: str
    rendered_prompt: str
    images: list[str]
    mappings: list[ShotFramePromptMappingRead]


def derive_frame_preview(
    *,
    base: FrameBaseDraft,
    context: FrameGenerationContext,
) -> FrameDerivedPreview:
    normalized_base_prompt = (base.prompt or "").strip()
    replaced_prompt = replace_reference_names_in_prompt(
        base_prompt=normalized_base_prompt,
        mappings=context.ordered_refs,
    )
    rendered_prompt = compose_shot_frame_rendered_prompt(
        replaced_prompt=replaced_prompt,
        mappings=context.ordered_refs,
    )
    return FrameDerivedPreview(
        shot_id=base.shot_id,
        frame_type=base.frame_type.value if hasattr(base.frame_type, "value") else str(base.frame_type),
        base_prompt=normalized_base_prompt,
        rendered_prompt=rendered_prompt,
        images=[mapping.file_id for mapping in context.ordered_refs],
        mappings=context.ordered_refs,
    )


def to_rendered_shot_frame_prompt_read(
    *,
    derived: FrameDerivedPreview,
) -> RenderedShotFramePromptRead:
    return RenderedShotFramePromptRead(
        base_prompt=derived.base_prompt,
        rendered_prompt=derived.rendered_prompt,
        images=derived.images,
        mappings=derived.mappings,
    )

