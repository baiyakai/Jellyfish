/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ShotFramePromptMappingRead } from './ShotFramePromptMappingRead';
/**
 * 关键帧最终生成提示词渲染结果。
 */
export type RenderedShotFramePromptRead = {
    /**
     * 原始基础提示词（不含图片映射说明）
     */
    base_prompt: string;
    /**
     * 最终提交给模型的提示词（含图片映射说明）
     */
    rendered_prompt: string;
    /**
     * 最终参考图 file_id 列表，顺序与 mappings 一致
     */
    images?: Array<string>;
    /**
     * 图片与实体名称的映射关系，顺序与 images 完全一致
     */
    mappings?: Array<ShotFramePromptMappingRead>;
};
