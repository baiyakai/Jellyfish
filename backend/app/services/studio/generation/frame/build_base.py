from __future__ import annotations

from app.models.studio import ShotFrameType
from app.services.studio.generation.shared.types import GenerationBaseDraft


class FrameBaseDraft(GenerationBaseDraft):
    """分镜帧图片生成的基础提示词真值。"""

    kind: str = "frame"
    shot_id: str
    frame_type: ShotFrameType
    prompt: str


def build_frame_base_draft(
    *,
    shot_id: str,
    frame_type: ShotFrameType,
    prompt: str,
) -> FrameBaseDraft:
    return FrameBaseDraft(
        shot_id=shot_id,
        frame_type=frame_type,
        prompt=(prompt or "").strip(),
    )

