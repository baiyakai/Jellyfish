from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ShotFramePromptInput(BaseModel):
    """镜头帧提示词生成输入，与 Shot + ShotDetail 字段对齐。"""

    model_config = ConfigDict(extra="forbid")

    script_excerpt: str = Field(..., description="剧本摘录，对应 Shot.script_excerpt")
    title: str = Field("", description="镜头标题，对应 Shot.title")
    visual_style: Optional[str] = Field(None, description="画面表现形式（现实/动漫等）")
    style: Optional[str] = Field(None, description="题材/风格")
    unify_style: Optional[bool] = Field(None, description="是否要求镜头间统一继承项目风格")
    camera_shot: Optional[str] = Field(None, description="景别，如 ECU/CU/MS")
    angle: Optional[str] = Field(None, description="机位角度")
    movement: Optional[str] = Field(None, description="运镜方式")
    atmosphere: Optional[str] = Field(None, description="氛围描述")
    shot_description: Optional[str] = Field(None, description="镜头整体描述或补充说明")
    mood_tags: Optional[List[str]] = Field(None, description="情绪标签")
    vfx_type: Optional[str] = Field(None, description="视效类型")
    vfx_note: Optional[str] = Field(None, description="视效说明")
    duration: Optional[int] = Field(None, description="时长（秒）")
    scene_id: Optional[str] = Field(None, description="关联场景 ID")
    dialog_summary: Optional[str] = Field(None, description="对白摘要")
    character_context: Optional[str] = Field(None, description="镜头已确认角色及描述")
    scene_context: Optional[str] = Field(None, description="镜头已确认场景及描述")
    prop_context: Optional[str] = Field(None, description="镜头已确认道具及描述")
    costume_context: Optional[str] = Field(None, description="镜头已确认服装及描述")
    subject_priority: Optional[str] = Field(None, description="主体优先级建议，说明本镜头应优先写谁、先写哪个场景")
    retry_guidance: Optional[str] = Field(None, description="自动重试时附加的修正要求")


class ShotFramePromptResult(BaseModel):
    """镜头帧提示词生成结果：单个 prompt 字符串。"""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(..., description="画面描述提示词，可写入 ShotDetail 对应字段")
    debug_context: dict[str, Any] | None = Field(None, description="本次生成使用的上下文，便于排查与调试")


__all__ = ["ShotFramePromptInput", "ShotFramePromptResult"]
