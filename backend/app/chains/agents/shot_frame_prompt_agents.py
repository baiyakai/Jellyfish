"""镜头分镜首帧/尾帧/关键帧提示词生成 Agent：根据镜头信息生成对应帧的画面提示词。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.prompts import PromptTemplate

from app.chains.agents.base import AgentBase, _extract_json_from_text
from app.schemas.skills.shot_frame_prompt import ShotFramePromptResult


def _prepare_shot_frame_input(input_dict: dict[str, Any]) -> dict[str, Any]:
    """将 input_dict 转为 prompt 模板所需格式，mood_tags 转为字符串。"""
    out = dict(input_dict)
    if "mood_tags" in out and isinstance(out["mood_tags"], list):
        out["mood_tags"] = ", ".join(str(t) for t in out["mood_tags"])
    else:
        out.setdefault("mood_tags", "")
    for key in (
        "visual_style",
        "style",
        "unify_style",
        "camera_shot",
        "angle",
        "movement",
        "atmosphere",
        "shot_description",
        "vfx_type",
        "vfx_note",
        "duration",
        "scene_id",
        "dialog_summary",
        "character_context",
        "scene_context",
        "prop_context",
        "costume_context",
        "subject_priority",
        "retry_guidance",
    ):
        if key not in out or out[key] is None:
            out[key] = ""
    if isinstance(out.get("unify_style"), bool):
        out["unify_style"] = "是" if out["unify_style"] else "否"
    out.setdefault("title", "")
    return out


_SHOT_FRAME_INPUT_VARS = [
    "script_excerpt",
    "title",
    "visual_style",
    "style",
    "unify_style",
    "camera_shot",
    "angle",
    "movement",
    "atmosphere",
    "shot_description",
    "mood_tags",
    "vfx_type",
    "vfx_note",
    "duration",
    "scene_id",
    "dialog_summary",
    "character_context",
    "scene_context",
    "prop_context",
    "costume_context",
    "subject_priority",
    "retry_guidance",
]

_FRAME_FOCUS = {
    "首帧": "优先描述镜头开始时最先看到的画面建立信息，强调开场定场、主体初始状态与进入情境的第一印象。",
    "尾帧": "优先描述镜头结束时最终停留的画面状态，强调动作收束、人物结束姿态、视线落点或情绪余韵。",
    "关键帧": "优先捕捉镜头中最具代表性、最有戏剧张力或信息密度最高的瞬间，不必平均描述整个过程。",
}

_SHOT_FRAME_TEMPLATE = """你是一名专业影视分镜提示词设计师，需要为同一项目中的镜头生成**{frame_name}基础提示词**。

你的任务是生成“基础提示词”，只描述画面本身，供后续系统继续拼接图片映射说明。

## 强约束
1. 必须继承项目级画面表现形式与题材风格：{visual_style} / {style}
2. 项目是否要求统一风格：{unify_style}
3. 若镜头信息不足，优先向项目风格与已确认实体设定收敛，不要自由发散到其他风格
4. 当前镜头已确认的角色、场景、道具、服装名称必须原样保留，不得翻译、不得改名、不得替换为同义词
5. 不得输出“图1/图2”、不得输出“## 图片内容说明”、不得输出引用映射说明
6. 输出应为一句或几句简洁、可视化、可直接用于图像生成模型的中文描述
7. 尽量保持统一描述口径，优先按“景别/机位/运镜 -> 场景环境 -> 主体人物/关键对象 -> 动作状态 -> 氛围情绪 -> 风格收束”组织
8. 只输出一个 JSON 对象：{{"prompt": "你的提示词内容"}}，不要输出其他文字
9. 当前帧关注重点：{frame_focus}
10. 主体优先级建议：{subject_priority}
11. 不要为了“写全信息”而平均罗列所有角色、道具、服装；优先突出主角色、主场景和主动作，其余元素仅在能强化当前画面时再进入提示词
12. 如果下面提供了“修正要求”，必须逐条满足后再输出最终结果

## 镜头信息
剧本摘录：{script_excerpt}
镜头标题：{title}
镜头补充描述：{shot_description}
景别：{camera_shot}
机位角度：{angle}
运镜：{movement}
氛围：{atmosphere}
情绪标签：{mood_tags}
视效：{vfx_type} - {vfx_note}
时长：{duration}秒
对白摘要：{dialog_summary}

## 已确认实体上下文
角色：{character_context}
场景：{scene_context}
道具：{prop_context}
服装：{costume_context}
修正要求：{retry_guidance}

## 输出（仅 {frame_name} 基础提示词，JSON：{{"prompt": "..."}}）
"""

def _build_frame_template(frame_name: str) -> str:
    return (
        _SHOT_FRAME_TEMPLATE.replace("{frame_name}", frame_name)
        .replace("{frame_focus}", _FRAME_FOCUS[frame_name])
    )


_FIRST_FRAME_TEMPLATE = _build_frame_template("首帧")
_LAST_FRAME_TEMPLATE = _build_frame_template("尾帧")
_KEY_FRAME_TEMPLATE = _build_frame_template("关键帧")

SHOT_FIRST_FRAME_PROMPT = PromptTemplate(input_variables=_SHOT_FRAME_INPUT_VARS, template=_FIRST_FRAME_TEMPLATE)
SHOT_LAST_FRAME_PROMPT = PromptTemplate(input_variables=_SHOT_FRAME_INPUT_VARS, template=_LAST_FRAME_TEMPLATE)
SHOT_KEY_FRAME_PROMPT = PromptTemplate(input_variables=_SHOT_FRAME_INPUT_VARS, template=_KEY_FRAME_TEMPLATE)


class ShotFirstFramePromptAgent(AgentBase[ShotFramePromptResult]):
    """镜头首帧提示词生成 Agent，输出可写入 ShotDetail.first_frame_prompt。"""

    @property
    def prompt_template(self) -> PromptTemplate:
        return SHOT_FIRST_FRAME_PROMPT

    @property
    def output_model(self) -> type[ShotFramePromptResult]:
        return ShotFramePromptResult

    def format_output(self, raw: str) -> ShotFramePromptResult:
        json_str = _extract_json_from_text(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return ShotFramePromptResult(prompt=raw.strip())
        if isinstance(data, dict) and "prompt" in data:
            return ShotFramePromptResult(prompt=str(data["prompt"]).strip())
        return ShotFramePromptResult(prompt=raw.strip())

    def extract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = self.run(**inp)
        return self.format_output(raw)

    async def aextract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = await self.arun(**inp)
        return self.format_output(raw)


class ShotLastFramePromptAgent(AgentBase[ShotFramePromptResult]):
    """镜头尾帧提示词生成 Agent，输出可写入 ShotDetail.last_frame_prompt。"""

    @property
    def prompt_template(self) -> PromptTemplate:
        return SHOT_LAST_FRAME_PROMPT

    @property
    def output_model(self) -> type[ShotFramePromptResult]:
        return ShotFramePromptResult

    def format_output(self, raw: str) -> ShotFramePromptResult:
        json_str = _extract_json_from_text(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return ShotFramePromptResult(prompt=raw.strip())
        if isinstance(data, dict) and "prompt" in data:
            return ShotFramePromptResult(prompt=str(data["prompt"]).strip())
        return ShotFramePromptResult(prompt=raw.strip())

    def extract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = self.run(**inp)
        return self.format_output(raw)

    async def aextract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = await self.arun(**inp)
        return self.format_output(raw)


class ShotKeyFramePromptAgent(AgentBase[ShotFramePromptResult]):
    """镜头关键帧提示词生成 Agent，输出可写入 ShotDetail.key_frame_prompt。"""

    @property
    def prompt_template(self) -> PromptTemplate:
        return SHOT_KEY_FRAME_PROMPT

    @property
    def output_model(self) -> type[ShotFramePromptResult]:
        return ShotFramePromptResult

    def format_output(self, raw: str) -> ShotFramePromptResult:
        json_str = _extract_json_from_text(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return ShotFramePromptResult(prompt=raw.strip())
        if isinstance(data, dict) and "prompt" in data:
            return ShotFramePromptResult(prompt=str(data["prompt"]).strip())
        return ShotFramePromptResult(prompt=raw.strip())

    def extract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = self.run(**inp)
        return self.format_output(raw)

    async def aextract(self, **kwargs: Any) -> ShotFramePromptResult:
        inp = _prepare_shot_frame_input(kwargs)
        raw = await self.arun(**inp)
        return self.format_output(raw)
