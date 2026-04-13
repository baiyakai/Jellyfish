from __future__ import annotations

from app.services.studio.generation.shared.types import GenerationBaseDraft


class VideoBaseDraft(GenerationBaseDraft):
    """视频生成的基础真值。"""

    kind: str = "video"
    shot_id: str
    prompt: str
    size: str | None = None


def build_video_base_draft(
    *,
    shot_id: str,
    prompt: str | None,
    size: str | None = None,
) -> VideoBaseDraft:
    return VideoBaseDraft(
        shot_id=shot_id,
        prompt=(prompt or "").strip(),
        size=(size or "").strip() or None,
    )

