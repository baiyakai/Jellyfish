/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_list_ShotExtractedCandidateRead__ } from '../models/ApiResponse_list_ShotExtractedCandidateRead__';
import type { ApiResponse_NoneType_ } from '../models/ApiResponse_NoneType_';
import type { ApiResponse_PaginatedData_ShotLinkedAssetItem__ } from '../models/ApiResponse_PaginatedData_ShotLinkedAssetItem__';
import type { ApiResponse_PaginatedData_ShotRead__ } from '../models/ApiResponse_PaginatedData_ShotRead__';
import type { ApiResponse_ShotAssetsOverviewRead_ } from '../models/ApiResponse_ShotAssetsOverviewRead_';
import type { ApiResponse_ShotExtractedCandidateRead_ } from '../models/ApiResponse_ShotExtractedCandidateRead_';
import type { ApiResponse_ShotRead_ } from '../models/ApiResponse_ShotRead_';
import type { ApiResponse_StudioScriptExtractionDraft_ } from '../models/ApiResponse_StudioScriptExtractionDraft_';
import type { ShotCreate } from '../models/ShotCreate';
import type { ShotExtractedCandidateLinkRequest } from '../models/ShotExtractedCandidateLinkRequest';
import type { ShotSkipExtractionUpdate } from '../models/ShotSkipExtractionUpdate';
import type { ShotUpdate } from '../models/ShotUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class StudioShotsService {
    /**
     * 镜头列表（分页）
     * @returns ApiResponse_PaginatedData_ShotRead__ Successful Response
     * @throws ApiError
     */
    public static listShotsApiV1StudioShotsGet({
        chapterId,
        q,
        order,
        isDesc = false,
        page = 1,
        pageSize = 10,
    }: {
        /**
         * 按章节过滤
         */
        chapterId?: (string | null),
        /**
         * 关键字，过滤 title/script_excerpt
         */
        q?: (string | null),
        order?: (string | null),
        isDesc?: boolean,
        page?: number,
        pageSize?: number,
    }): CancelablePromise<ApiResponse_PaginatedData_ShotRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/shots',
            query: {
                'chapter_id': chapterId,
                'q': q,
                'order': order,
                'is_desc': isDesc,
                'page': page,
                'page_size': pageSize,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 创建镜头
     * @returns ApiResponse_ShotRead_ Successful Response
     * @throws ApiError
     */
    public static createShotApiV1StudioShotsPost({
        requestBody,
    }: {
        requestBody: ShotCreate,
    }): CancelablePromise<ApiResponse_ShotRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/shots',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 分镜详情：按镜头关联拼装 StudioScriptExtractionDraft
     * @returns ApiResponse_StudioScriptExtractionDraft_ Successful Response
     * @throws ApiError
     */
    public static getShotExtractionDraftApiV1StudioShotsShotIdExtractionDraftGet({
        shotId,
    }: {
        shotId: string,
    }): CancelablePromise<ApiResponse_StudioScriptExtractionDraft_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/shots/{shot_id}/extraction-draft',
            path: {
                'shot_id': shotId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取镜头提取候选项
     * @returns ApiResponse_list_ShotExtractedCandidateRead__ Successful Response
     * @throws ApiError
     */
    public static getShotExtractedCandidatesApiV1StudioShotsShotIdExtractedCandidatesGet({
        shotId,
    }: {
        shotId: string,
    }): CancelablePromise<ApiResponse_list_ShotExtractedCandidateRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/shots/{shot_id}/extracted-candidates',
            path: {
                'shot_id': shotId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取镜头资产总览（已关联资产 + 提取候选）
     * @returns ApiResponse_ShotAssetsOverviewRead_ Successful Response
     * @throws ApiError
     */
    public static getShotAssetsOverviewApiApiV1StudioShotsShotIdAssetsOverviewGet({
        shotId,
    }: {
        shotId: string,
    }): CancelablePromise<ApiResponse_ShotAssetsOverviewRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/shots/{shot_id}/assets-overview',
            path: {
                'shot_id': shotId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 设置是否跳过镜头信息提取
     * @returns ApiResponse_ShotRead_ Successful Response
     * @throws ApiError
     */
    public static updateShotSkipExtractionApiV1StudioShotsShotIdSkipExtractionPatch({
        shotId,
        requestBody,
    }: {
        shotId: string,
        requestBody: ShotSkipExtractionUpdate,
    }): CancelablePromise<ApiResponse_ShotRead_> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/studio/shots/{shot_id}/skip-extraction',
            path: {
                'shot_id': shotId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 确认并关联镜头提取候选项
     * @returns ApiResponse_ShotExtractedCandidateRead_ Successful Response
     * @throws ApiError
     */
    public static linkExtractedCandidateApiV1StudioShotsExtractedCandidatesCandidateIdLinkPatch({
        candidateId,
        requestBody,
    }: {
        candidateId: number,
        requestBody: ShotExtractedCandidateLinkRequest,
    }): CancelablePromise<ApiResponse_ShotExtractedCandidateRead_> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/studio/shots/extracted-candidates/{candidate_id}/link',
            path: {
                'candidate_id': candidateId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 忽略镜头提取候选项
     * @returns ApiResponse_ShotExtractedCandidateRead_ Successful Response
     * @throws ApiError
     */
    public static ignoreExtractedCandidateApiV1StudioShotsExtractedCandidatesCandidateIdIgnorePatch({
        candidateId,
    }: {
        candidateId: number,
    }): CancelablePromise<ApiResponse_ShotExtractedCandidateRead_> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/studio/shots/extracted-candidates/{candidate_id}/ignore',
            path: {
                'candidate_id': candidateId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取镜头
     * @returns ApiResponse_ShotRead_ Successful Response
     * @throws ApiError
     */
    public static getShotApiV1StudioShotsShotIdGet({
        shotId,
    }: {
        shotId: string,
    }): CancelablePromise<ApiResponse_ShotRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/shots/{shot_id}',
            path: {
                'shot_id': shotId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新镜头
     * @returns ApiResponse_ShotRead_ Successful Response
     * @throws ApiError
     */
    public static updateShotApiV1StudioShotsShotIdPatch({
        shotId,
        requestBody,
    }: {
        shotId: string,
        requestBody: ShotUpdate,
    }): CancelablePromise<ApiResponse_ShotRead_> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/studio/shots/{shot_id}',
            path: {
                'shot_id': shotId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除镜头
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteShotApiV1StudioShotsShotIdDelete({
        shotId,
    }: {
        shotId: string,
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/shots/{shot_id}',
            path: {
                'shot_id': shotId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取镜头关联的角色/道具/场景/服装（分页）
     * @returns ApiResponse_PaginatedData_ShotLinkedAssetItem__ Successful Response
     * @throws ApiError
     */
    public static listShotLinkedAssetsApiV1StudioShotsShotIdLinkedAssetsGet({
        shotId,
        page = 1,
        pageSize = 10,
    }: {
        shotId: string,
        page?: number,
        pageSize?: number,
    }): CancelablePromise<ApiResponse_PaginatedData_ShotLinkedAssetItem__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/shots/{shot_id}/linked-assets',
            path: {
                'shot_id': shotId,
            },
            query: {
                'page': page,
                'page_size': pageSize,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
