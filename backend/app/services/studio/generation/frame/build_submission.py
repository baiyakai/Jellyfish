from __future__ import annotations

from app.services.studio.generation.frame.build_base import FrameBaseDraft
from app.services.studio.generation.frame.build_context import FrameGenerationContext
from app.services.studio.generation.frame.derive_preview import derive_frame_preview
from app.services.studio.generation.shared.types import GenerationSubmissionPayload


def build_frame_submission_payload(
    *,
    base: FrameBaseDraft,
    context: FrameGenerationContext,
) -> GenerationSubmissionPayload:
    derived = derive_frame_preview(base=base, context=context)
    return GenerationSubmissionPayload(
        kind="frame",
        prompt=derived.rendered_prompt,
        images=derived.images,
        extra={
            "render_context": {
                "base_prompt": derived.base_prompt,
                "rendered_prompt": derived.rendered_prompt,
                "images": derived.images,
                "mappings": [mapping.model_dump() for mapping in derived.mappings],
            }
        },
    )
