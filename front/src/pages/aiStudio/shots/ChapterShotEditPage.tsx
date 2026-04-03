import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Divider, Empty, Input, Layout, List, Modal, Popconfirm, Spin, Tag, Tooltip, Typography, message } from 'antd'
import { ArrowLeftOutlined, DeleteOutlined, FireOutlined, PlusOutlined, SaveOutlined, SmileOutlined } from '@ant-design/icons'
import type {
  EntityNameExistenceItem,
  ShotAssetOverviewItem,
  ShotAssetsOverviewRead,
  ShotDialogLineCreate,
  ShotDialogLineRead,
  ShotDialogLineUpdate,
  ShotRead,
  StudioShotDraftDialogueLine,
} from '../../../services/generated'
import {
  ScriptProcessingService,
  StudioChaptersService,
  StudioEntitiesService,
  StudioProjectsService,
  StudioShotDialogLinesService,
  StudioShotsService,
  StudioShotCharacterLinksService,
  StudioShotLinksService,
} from '../../../services/generated'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { getChapterShotsPath } from '../project/ProjectWorkbench/routes'
import { DisplayImageCard } from '../assets/components/DisplayImageCard'
import { StudioEntitiesApi } from '../../../services/studioEntities'
import { resolveAssetUrl } from '../assets/utils'

const { Header, Content } = Layout

type AssetKind = 'scene' | 'actor' | 'prop' | 'costume'
type NamedDraft = { name: string; thumbnail?: string | null; id?: string | null; file_id?: string | null; description?: string | null }
type AssetVM = NamedDraft & {
  kind: AssetKind
  status: 'linked' | 'new'
  candidateId?: number
  candidateStatus?: ShotAssetOverviewItem['candidate_status']
}
type ExtractedDialogLineVM = StudioShotDraftDialogueLine & { __key: string }

function dialogTitle(speaker?: string | null, target?: string | null) {
  const s = (speaker ?? '').trim() || '未知'
  const t = (target ?? '').trim() || '未知'
  return `${s} → ${t}`
}

function assetDetailUrl(kind: AssetKind, id: string, projectId: string) {
  if (kind === 'scene') return `/assets/scenes/${encodeURIComponent(id)}/edit`
  if (kind === 'prop') return `/assets/props/${encodeURIComponent(id)}/edit`
  if (kind === 'costume') return `/assets/costumes/${encodeURIComponent(id)}/edit`
  // actor/角色：跳转项目角色编辑页（character）
  return `/projects/${encodeURIComponent(projectId)}/roles/${encodeURIComponent(id)}/edit`
}

function overviewTypeToAssetKind(kind: ShotAssetOverviewItem['type']): AssetKind {
  return kind === 'character' ? 'actor' : kind
}

export function ChapterShotEditPage() {
  const navigate = useNavigate()
  const { projectId, chapterId, shotId } = useParams<{
    projectId: string
    chapterId: string
    shotId: string
  }>()

  const [chapterTitle, setChapterTitle] = useState('')
  const [chapterIndex, setChapterIndex] = useState<number | null>(null)
  const [projectVisualStyle, setProjectVisualStyle] = useState<'现实' | '动漫'>('现实')
  const [projectStyle, setProjectStyle] = useState<string>('真人都市')
  const [shots, setShots] = useState<ShotRead[]>([])
  const [shot, setShot] = useState<ShotRead | null>(null)
  const [title, setTitle] = useState('')
  const [scriptExcerpt, setScriptExcerpt] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [shotAssetsOverview, setShotAssetsOverview] = useState<ShotAssetsOverviewRead | null>(null)
  const assetsOverviewRequestSeqRef = useRef(0)
  const [extractingAssets, setExtractingAssets] = useState(false)
  const [skipExtractionUpdating, setSkipExtractionUpdating] = useState(false)
  const extractInFlightRef = useRef(false)

  const [linkingOpen, setLinkingOpen] = useState(false)
  const [linkingLoading, setLinkingLoading] = useState(false)
  const [linkingActionLoading, setLinkingActionLoading] = useState(false)
  const [linkingHint, setLinkingHint] = useState<string>('')
  const [linkingKind, setLinkingKind] = useState<AssetKind>('scene')
  const [linkingName, setLinkingName] = useState<string>('')
  const [linkingThumb, setLinkingThumb] = useState<string | undefined>(undefined)
  const [linkingItem, setLinkingItem] = useState<EntityNameExistenceItem | null>(null)

  const [existenceByKindName, setExistenceByKindName] = useState<Record<AssetKind, Record<string, EntityNameExistenceItem>>>({
    scene: {},
    actor: {},
    prop: {},
    costume: {},
  })
  const existenceInFlightRef = useRef<Record<AssetKind, boolean>>({
    scene: false,
    actor: false,
    prop: false,
    costume: false,
  })

  const [dialogLoading, setDialogLoading] = useState(false)
  const [savedDialogLines, setSavedDialogLines] = useState<ShotDialogLineRead[]>([])
  const [extractedDialogLines, setExtractedDialogLines] = useState<ExtractedDialogLineVM[]>([])
  const [dialogDeletingIds, setDialogDeletingIds] = useState<Record<number, boolean>>({})
  const [dialogSavingIds, setDialogSavingIds] = useState<Record<number, boolean>>({})
  const [dialogAddingKeys, setDialogAddingKeys] = useState<Record<string, boolean>>({})
  const [batchDialogAdding, setBatchDialogAdding] = useState(false)
  const [candidateActionIds, setCandidateActionIds] = useState<Record<number, boolean>>({})
  const dialogDebounceTimersRef = useRef<Map<number, number>>(new Map())

  const shotsSorted = useMemo(
    () => [...shots].sort((a, b) => a.index - b.index),
    [shots],
  )

  const unionAssets = useMemo(() => {
    const groups: Record<AssetKind, AssetVM[]> = {
      scene: [],
      actor: [],
      prop: [],
      costume: [],
    }
    for (const item of shotAssetsOverview?.items ?? []) {
      if (item.candidate_status === 'ignored') continue
      const kind = overviewTypeToAssetKind(item.type)
      groups[kind].push({
        kind,
        name: item.name,
        thumbnail: item.thumbnail ?? null,
        id: item.linked_entity_id ?? null,
        file_id: item.file_id ?? null,
        description: item.description ?? null,
        status: item.is_linked ? 'linked' : 'new',
        candidateId: item.candidate_id ?? undefined,
        candidateStatus: item.candidate_status ?? undefined,
      })
    }
    return groups
  }, [shotAssetsOverview])

  const [expandedKinds, setExpandedKinds] = useState<Record<AssetKind, boolean>>({
    scene: false,
    actor: false,
    prop: false,
    costume: false,
  })

  const toggleExpanded = (kind: AssetKind) => {
    setExpandedKinds((prev) => ({ ...prev, [kind]: !prev[kind] }))
  }

  const loadPage = useCallback(async () => {
    if (!chapterId || !shotId || !projectId) return
    setLoading(true)
    try {
      const [projectRes, chRes, listRes, shotRes] = await Promise.all([
        StudioProjectsService.getProjectApiV1StudioProjectsProjectIdGet({ projectId }),
        StudioChaptersService.getChapterApiV1StudioChaptersChapterIdGet({ chapterId }),
        StudioShotsService.listShotsApiV1StudioShotsGet({
          chapterId,
          page: 1,
          pageSize: 100,
          order: 'index',
          isDesc: false,
        }),
        StudioShotsService.getShotApiV1StudioShotsShotIdGet({ shotId }),
      ])
      const nextVisualStyle = projectRes.data?.visual_style
      const nextStyle = projectRes.data?.style
      if (nextVisualStyle === '现实' || nextVisualStyle === '动漫') {
        setProjectVisualStyle(nextVisualStyle)
      }
      if (typeof nextStyle === 'string' && nextStyle.trim()) {
        setProjectStyle(nextStyle)
      }

      const c = chRes.data
      setChapterTitle(c?.title ?? '')
      setChapterIndex(typeof c?.index === 'number' ? c.index : null)

      const items = listRes.data?.items ?? []
      setShots(items)

      const s = shotRes.data
      if (!s) {
        message.error('分镜不存在')
        navigate(getChapterShotsPath(projectId, chapterId), { replace: true })
        return
      }
      if (s.chapter_id !== chapterId) {
        message.error('分镜不属于当前章节')
        navigate(getChapterShotsPath(projectId, chapterId), { replace: true })
        return
      }

      setShot(s)
      setTitle(s.title ?? '')
      setScriptExcerpt(s.script_excerpt ?? '')
      setShotAssetsOverview(null)
      setSavedDialogLines([])
      setExtractedDialogLines([])
    } catch {
      message.error('加载失败')
      navigate(getChapterShotsPath(projectId, chapterId), { replace: true })
    } finally {
      setLoading(false)
    }
  }, [chapterId, navigate, projectId, shotId])

  const clearDialogDebounceTimers = useCallback(() => {
    for (const [, timer] of dialogDebounceTimersRef.current.entries()) {
      window.clearTimeout(timer)
    }
    dialogDebounceTimersRef.current.clear()
  }, [])

  const loadAssetsOverview = useCallback(async () => {
    if (!shotId) return
    const reqSeq = ++assetsOverviewRequestSeqRef.current
    try {
      const res = await StudioShotsService.getShotAssetsOverviewApiApiV1StudioShotsShotIdAssetsOverviewGet({
        shotId,
      })
      if (reqSeq !== assetsOverviewRequestSeqRef.current) return
      setShotAssetsOverview(res.data ?? null)
    } catch {
      if (reqSeq !== assetsOverviewRequestSeqRef.current) return
      setShotAssetsOverview(null)
    }
  }, [shotId])

  const loadDialogLines = useCallback(async () => {
    if (!shotId) return
    setDialogLoading(true)
    try {
      const all: ShotDialogLineRead[] = []
      let page = 1
      const pageSize = 100
      let total: number | null = null
      while (true) {
        const res = await StudioShotDialogLinesService.listShotDialogLinesApiV1StudioShotDialogLinesGet({
          shotDetailId: shotId,
          page,
          pageSize,
          order: 'index',
          isDesc: false,
        })
        const data = res.data
        const items = data?.items ?? []
        if (typeof data?.pagination?.total === 'number') total = data.pagination.total
        all.push(...items)
        if (items.length < pageSize) break
        if (typeof total === 'number' && all.length >= total) break
        page += 1
      }
      setSavedDialogLines(all)
    } catch {
      message.error('对白加载失败')
    } finally {
      setDialogLoading(false)
    }
  }, [shotId])

  const scheduleSaveDialogLine = useCallback(
    (lineId: number, patch: ShotDialogLineUpdate) => {
      const prev = dialogDebounceTimersRef.current.get(lineId)
      if (prev) window.clearTimeout(prev)
      const timer = window.setTimeout(async () => {
        setDialogSavingIds((m) => ({ ...m, [lineId]: true }))
        try {
          await StudioShotDialogLinesService.updateShotDialogLineApiV1StudioShotDialogLinesLineIdPatch({
            lineId,
            requestBody: patch,
          })
        } catch {
          message.error('对白保存失败')
        } finally {
          setDialogSavingIds((m) => ({ ...m, [lineId]: false }))
        }
      }, 1000)
      dialogDebounceTimersRef.current.set(lineId, timer)
    },
    [],
  )

  const updateSavedDialogText = useCallback(
    (lineId: number, text: string) => {
      setSavedDialogLines((prev) => prev.map((l) => (l.id === lineId ? { ...l, text } : l)))
      scheduleSaveDialogLine(lineId, { text })
    },
    [scheduleSaveDialogLine],
  )

  const deleteSavedDialogLine = useCallback(
    async (lineId: number) => {
      if (dialogDeletingIds[lineId]) return
      const prevTimer = dialogDebounceTimersRef.current.get(lineId)
      if (prevTimer) window.clearTimeout(prevTimer)
      dialogDebounceTimersRef.current.delete(lineId)
      setDialogDeletingIds((m) => ({ ...m, [lineId]: true }))
      try {
        await StudioShotDialogLinesService.deleteShotDialogLineApiV1StudioShotDialogLinesLineIdDelete({ lineId })
        setSavedDialogLines((prev) => prev.filter((l) => l.id !== lineId))
        message.success('已删除')
      } catch {
        message.error('删除失败')
      } finally {
        setDialogDeletingIds((m) => ({ ...m, [lineId]: false }))
      }
    },
    [dialogDeletingIds],
  )

  const updateExtractedDialogText = useCallback((key: string, text: string) => {
    setExtractedDialogLines((prev) => prev.map((l) => (l.__key === key ? { ...l, text } : l)))
  }, [])

  const createDialogLine = useCallback(
    async (line: ExtractedDialogLineVM, options?: { silent?: boolean }) => {
      if (!shotId) return null
      const text = (line.text ?? '').trim()
      if (!text) {
        if (!options?.silent) message.warning('请先填写对白内容')
        return null
      }
      const maxIndex = savedDialogLines.reduce((m, it) => Math.max(m, typeof it.index === 'number' ? it.index : -1), -1)
      const index = typeof line.index === 'number' ? line.index : maxIndex + 1
      const body: ShotDialogLineCreate = {
        shot_detail_id: shotId,
        index,
        text,
        line_mode: line.line_mode,
        speaker_name: line.speaker_name ?? null,
        target_name: line.target_name ?? null,
      }
      const res = await StudioShotDialogLinesService.createShotDialogLineApiV1StudioShotDialogLinesPost({ requestBody: body })
      return res.data ?? null
    },
    [savedDialogLines, shotId],
  )

  const addExtractedDialogLine = useCallback(
    async (line: ExtractedDialogLineVM) => {
      if (dialogAddingKeys[line.__key]) return
      setDialogAddingKeys((m) => ({ ...m, [line.__key]: true }))
      try {
        const created = await createDialogLine(line)
        if (created) {
          setSavedDialogLines((prev) => [...prev, created].sort((a, b) => (a.index ?? 0) - (b.index ?? 0)))
          setExtractedDialogLines((prev) => prev.filter((x) => x.__key !== line.__key))
          message.success('已添加')
        }
      } catch {
        message.error('添加失败')
      } finally {
        setDialogAddingKeys((m) => ({ ...m, [line.__key]: false }))
      }
    },
    [createDialogLine, dialogAddingKeys],
  )

  const acceptAllExtractedDialogLines = useCallback(async () => {
    if (batchDialogAdding || extractedDialogLines.length === 0) return
    setBatchDialogAdding(true)
    try {
      const accepted: ShotDialogLineRead[] = []
      const remaining: ExtractedDialogLineVM[] = []
      for (const line of extractedDialogLines) {
        try {
          const created = await createDialogLine(line, { silent: true })
          if (created) accepted.push(created)
          else remaining.push(line)
        } catch {
          remaining.push(line)
        }
      }
      if (accepted.length > 0) {
        setSavedDialogLines((prev) => [...prev, ...accepted].sort((a, b) => (a.index ?? 0) - (b.index ?? 0)))
      }
      setExtractedDialogLines(remaining)
      if (accepted.length === extractedDialogLines.length) {
        message.success(`已接受 ${accepted.length} 条对白`)
      } else if (accepted.length > 0) {
        message.warning(`已接受 ${accepted.length} 条，对剩余 ${remaining.length} 条请逐条检查`)
      } else {
        message.error('批量接受失败')
      }
    } finally {
      setBatchDialogAdding(false)
    }
  }, [batchDialogAdding, createDialogLine, extractedDialogLines])

  const ignoreAllExtractedDialogLines = useCallback(() => {
    if (batchDialogAdding || extractedDialogLines.length === 0) return
    setExtractedDialogLines([])
    message.success('已忽略本轮提取对白')
  }, [batchDialogAdding, extractedDialogLines.length])

  useEffect(() => {
    void loadPage()
  }, [loadPage])

  useEffect(() => {
    void loadAssetsOverview()
  }, [loadAssetsOverview])

  // 切换分镜时：清理对白防抖并拉取对白列表
  useEffect(() => {
    clearDialogDebounceTimers()
    void loadDialogLines()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shotId])

  useEffect(() => () => clearDialogDebounceTimers(), [clearDialogDebounceTimers])

  const saveShot = useCallback(async () => {
    if (!shot || !title.trim()) {
      message.warning('请填写标题')
      return
    }
    setSaving(true)
    try {
      const res = await StudioShotsService.updateShotApiV1StudioShotsShotIdPatch({
        shotId: shot.id,
        requestBody: {
          title: title.trim(),
          script_excerpt: scriptExcerpt.trim() ? scriptExcerpt.trim() : null,
        },
      })
      const next = res.data
      if (next) {
        setShot(next)
        setShots((prev) => prev.map((x) => (x.id === next.id ? next : x)))
        message.success('已保存')
      }
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }, [scriptExcerpt, shot, title])

  const updateSkipExtraction = useCallback(
    async (skip: boolean) => {
      if (!shotId) return
      setSkipExtractionUpdating(true)
      try {
        const res = await StudioShotsService.updateShotSkipExtractionApiV1StudioShotsShotIdSkipExtractionPatch({
          shotId,
          requestBody: { skip },
        })
        const nextShot = res.data ?? null
        if (nextShot) {
          setShot(nextShot)
          setShots((prev) => prev.map((item) => (item.id === shotId ? { ...item, ...nextShot } : item)))
        } else {
          setShot((prev) => (prev ? { ...prev, skip_extraction: skip } : prev))
          setShots((prev) => prev.map((item) => (item.id === shotId ? { ...item, skip_extraction: skip } : item)))
        }
        await loadAssetsOverview()
        message.success(skip ? '已标记为无需提取' : '已恢复提取确认流程')
      } catch {
        message.error(skip ? '标记无需提取失败' : '恢复提取失败')
      } finally {
        setSkipExtractionUpdating(false)
      }
    },
    [loadAssetsOverview, shotId],
  )

  const extractAssets = useCallback(async () => {
    if (!projectId || !chapterId || !shot) return
    if (extractInFlightRef.current) return
    extractInFlightRef.current = true
    setExtractingAssets(true)
    try {
      const scriptDivision = {
        total_shots: 1,
        shots: [
          {
            index: shot.index,
            start_line: 1,
            end_line: 1,
            script_excerpt: shot.script_excerpt ?? '',
            shot_name: shot.title ?? '',
          },
        ],
      }
      const res = await ScriptProcessingService.extractScriptApiV1ScriptProcessingExtractPost({
        requestBody: {
          project_id: projectId,
          chapter_id: chapterId,
          script_division: scriptDivision as any,
          consistency: undefined,
          refresh_cache: false,
        } as any,
      })
      const next = res.data
      if (next) {
        const extractedLines = ((next.shots?.[0] as any)?.dialogue_lines ?? []) as StudioShotDraftDialogueLine[]
        const savedKeys = new Set(
          savedDialogLines.map((l) => `${(l.speaker_name ?? '').trim()}|${(l.target_name ?? '').trim()}|${(l.text ?? '').trim()}`),
        )
        const nextVM: ExtractedDialogLineVM[] = extractedLines
          .filter((l) => l?.text?.trim())
          .filter((l) => !savedKeys.has(`${(l.speaker_name ?? '').trim()}|${(l.target_name ?? '').trim()}|${(l.text ?? '').trim()}`))
          .map((l, i) => ({ ...l, __key: `${Date.now()}-${i}-${Math.random().toString(16).slice(2)}` }))
        setExtractedDialogLines((prev) => {
          const prevKeys = new Set(
            prev.map((l) => `${(l.speaker_name ?? '').trim()}|${(l.target_name ?? '').trim()}|${(l.text ?? '').trim()}`),
          )
          const merged = [...prev]
          for (const l of nextVM) {
            const k = `${(l.speaker_name ?? '').trim()}|${(l.target_name ?? '').trim()}|${(l.text ?? '').trim()}`
            if (prevKeys.has(k)) continue
            merged.push(l)
          }
          return merged
        })
        if (res.meta?.from_cache) {
          message.success('已从缓存加载提取结果；页面会优先展示数据表中的待确认候选')
        } else {
          message.success('提取完成；页面会优先展示数据表中的待确认候选')
        }
        await loadAssetsOverview()
      } else {
        message.error(res.message || '提取失败')
      }
    } catch {
      message.error('提取失败')
    } finally {
      setExtractingAssets(false)
      extractInFlightRef.current = false
    }
  }, [chapterId, loadAssetsOverview, projectId, savedDialogLines, shot])

  const goShot = (id: string) => {
    if (!projectId || !chapterId || id === shotId) return
    navigate(`/projects/${projectId}/chapters/${chapterId}/shots/${id}/edit`)
  }

  const openLinkingModal = useCallback(
    async (kind: AssetKind, name: string, item: EntityNameExistenceItem, hint: string) => {
      setLinkingKind(kind)
      setLinkingName(name)
      setLinkingItem(item)
      setLinkingHint(hint)
      setLinkingThumb(undefined)
      setLinkingOpen(true)
      if (!item.asset_id) return
      setLinkingLoading(true)
      try {
        const entityType =
          kind === 'scene' ? 'scene' : kind === 'prop' ? 'prop' : kind === 'costume' ? 'costume' : 'character'
        const res = await StudioEntitiesApi.get(entityType as any, item.asset_id)
        const data: any = res.data
        const thumb = resolveAssetUrl(data?.thumbnail ?? data?.images?.[0]?.thumbnail ?? '')
        setLinkingThumb(thumb || undefined)
      } catch {
        // ignore
      } finally {
        setLinkingLoading(false)
      }
    },
    [],
  )

  const doLink = useCallback(async () => {
    if (!projectId || !chapterId || !shotId) return
    if (!linkingItem?.asset_id) return
    setLinkingActionLoading(true)
    try {
      const asset_id = linkingItem.asset_id
      if (linkingKind === 'scene') {
        await StudioShotLinksService.createProjectSceneLinkApiV1StudioShotLinksScenePost({
          requestBody: { project_id: projectId, chapter_id: chapterId, shot_id: shotId, asset_id },
        })
      } else if (linkingKind === 'prop') {
        await StudioShotLinksService.createProjectPropLinkApiV1StudioShotLinksPropPost({
          requestBody: { project_id: projectId, chapter_id: chapterId, shot_id: shotId, asset_id },
        })
      } else if (linkingKind === 'costume') {
        await StudioShotLinksService.createProjectCostumeLinkApiV1StudioShotLinksCostumePost({
          requestBody: { project_id: projectId, chapter_id: chapterId, shot_id: shotId, asset_id },
        })
      } else {
        // 角色关联：追加到最后（maxIndex + 1）
        const linksRes = await StudioShotCharacterLinksService.listShotCharacterLinksApiV1StudioShotCharacterLinksGet({
          shotId,
        })
        const links = (linksRes.data ?? []) as Array<{ index?: number | null }>
        const maxIndex = links.reduce((m, it) => Math.max(m, typeof it?.index === 'number' ? it.index : -1), -1)
        await StudioShotCharacterLinksService.upsertShotCharacterLinkApiV1StudioShotCharacterLinksPost({
          requestBody: { shot_id: shotId, character_id: asset_id, index: maxIndex + 1 },
        })
      }
      message.success('已关联')
      await loadAssetsOverview()
      setLinkingOpen(false)
    } catch {
      message.error('关联失败')
    } finally {
      setLinkingActionLoading(false)
    }
  }, [chapterId, linkingItem?.asset_id, linkingKind, loadAssetsOverview, projectId, shotId])

  const handleNewAsset = useCallback(
    async (asset: AssetVM) => {
      if (!projectId || !chapterId || !shotId) return
      const name = asset.name.trim()
      if (!name) return
      try {
        const req: any = { project_id: projectId, shot_id: shotId }
        if (asset.kind === 'scene') req.scene_names = [name]
        else if (asset.kind === 'prop') req.prop_names = [name]
        else if (asset.kind === 'costume') req.costume_names = [name]
        else req.character_names = [name]

        const res = await StudioEntitiesService.checkEntityNamesExistenceApiV1StudioEntitiesExistenceCheckPost({
          requestBody: req,
        })
        const data = res.data
        const bucket =
          asset.kind === 'scene'
            ? data?.scenes
            : asset.kind === 'prop'
              ? data?.props
              : asset.kind === 'costume'
                ? data?.costumes
                : data?.characters
        const item = (bucket?.[0] as EntityNameExistenceItem | undefined) ?? null
        if (!item) {
          message.error('existence-check 返回为空')
          return
        }

        if (!item.exists) {
          Modal.confirm({
            title: '当前无可关联资产，是否新建？',
            okText: '新建',
            cancelText: '取消',
            onOk: () => {
              const open = (url: string) => window.open(url, '_blank', 'noopener,noreferrer')
              const descQ = asset.description?.trim()
                ? `&desc=${encodeURIComponent(asset.description.trim())}`
                : ''
              const styleQ =
                `&visualStyle=${encodeURIComponent(projectVisualStyle)}` +
                `&style=${encodeURIComponent(projectStyle)}`
              const ctxQ =
                `&projectId=${encodeURIComponent(projectId)}` +
                `&chapterId=${encodeURIComponent(chapterId)}` +
                `&shotId=${encodeURIComponent(shotId)}` +
                styleQ
              if (asset.kind === 'scene' || asset.kind === 'prop' || asset.kind === 'costume') {
                open(
                  `/assets?tab=${asset.kind}&create=1&name=${encodeURIComponent(name)}${descQ}${ctxQ}`,
                )
                return
              }
              open(
                `/projects/${encodeURIComponent(projectId)}?tab=roles&create=1&name=${encodeURIComponent(name)}${descQ}${ctxQ}`,
              )
            },
          })
          return
        }

        if (item.exists && !item.linked_to_project) {
          await openLinkingModal(asset.kind, name, item, '在资产库中存在同名资产，可关联')
          return
        }
        if (item.exists && item.linked_to_project && !item.linked_to_shot) {
          await openLinkingModal(asset.kind, name, item, '项目中存在同名资产，可关联')
          return
        }

        message.info('该资产已关联到当前镜头')
      } catch {
        message.error('existence-check 调用失败')
      }
    },
    [openLinkingModal, chapterId, projectId, projectStyle, projectVisualStyle, shotId],
  )

  const ignoreCandidate = useCallback(
    async (asset: AssetVM) => {
      if (!asset.candidateId) return
      if (candidateActionIds[asset.candidateId]) return
      setCandidateActionIds((prev) => ({ ...prev, [asset.candidateId!]: true }))
      try {
        await StudioShotsService.ignoreExtractedCandidateApiV1StudioShotsExtractedCandidatesCandidateIdIgnorePatch({
          candidateId: asset.candidateId,
        })
        await loadAssetsOverview()
        message.success('已忽略该候选项')
      } catch {
        message.error('忽略失败')
      } finally {
        setCandidateActionIds((prev) => ({ ...prev, [asset.candidateId!]: false }))
      }
    },
    [candidateActionIds, loadAssetsOverview],
  )


  const prefetchExistenceForNewAssets = useCallback(
    async (kind: AssetKind, items: AssetVM[]) => {
      if (!projectId || !shotId) return
      if (existenceInFlightRef.current[kind]) return
      const missingNames = items
        .filter((x) => x.status === 'new')
        .map((x) => x.name.trim())
        .filter(Boolean)
        .filter((n) => !existenceByKindName[kind][n])
      if (missingNames.length === 0) return

      existenceInFlightRef.current[kind] = true
      try {
        const req: any = { project_id: projectId, shot_id: shotId }
        if (kind === 'scene') req.scene_names = missingNames
        else if (kind === 'prop') req.prop_names = missingNames
        else if (kind === 'costume') req.costume_names = missingNames
        else req.character_names = missingNames

        const res = await StudioEntitiesService.checkEntityNamesExistenceApiV1StudioEntitiesExistenceCheckPost({
          requestBody: req,
        })
        const data = res.data
        const bucket =
          kind === 'scene'
            ? data?.scenes
            : kind === 'prop'
              ? data?.props
              : kind === 'costume'
                ? data?.costumes
                : data?.characters
        const list = Array.isArray(bucket) ? (bucket as EntityNameExistenceItem[]) : []
        if (list.length === 0) return
        setExistenceByKindName((prev) => {
          const next = { ...prev, [kind]: { ...prev[kind] } }
          for (const it of list) {
            const key = it?.name?.trim?.() ? it.name.trim() : ''
            if (!key) continue
            next[kind][key] = it
          }
          return next
        })
      } catch {
        // 静默：避免频繁 toast
      } finally {
        existenceInFlightRef.current[kind] = false
      }
    },
    [existenceByKindName, projectId, shotId],
  )

  useEffect(() => {
    void prefetchExistenceForNewAssets('scene', unionAssets.scene)
    void prefetchExistenceForNewAssets('actor', unionAssets.actor)
    void prefetchExistenceForNewAssets('prop', unionAssets.prop)
    void prefetchExistenceForNewAssets('costume', unionAssets.costume)
  }, [prefetchExistenceForNewAssets, unionAssets])

  const renderAssetCard = (asset: AssetVM) => {
    const existence = existenceByKindName[asset.kind][asset.name]
    const actionLabel = existence ? (existence.exists ? '关联' : '新建') : '…'
    const candidateBusy = asset.candidateId ? !!candidateActionIds[asset.candidateId] : false
    const footer =
      asset.status === 'new' ? (
        <div className="flex items-center justify-between gap-2">
          <div className="text-[11px] text-gray-500 truncate">
            {existence
              ? existence.linked_to_project
                ? '项目内可关联'
                : existence.exists
                  ? '资产库已有'
                  : '需新建'
              : '正在检查…'}
          </div>
          <div className="flex items-center gap-1">
            {asset.candidateId ? (
              <Button
                size="small"
                type="text"
                danger
                loading={candidateBusy}
                onClick={() => void ignoreCandidate(asset)}
              >
                忽略
              </Button>
            ) : null}
            <Button size="small" disabled={!existence || candidateBusy} onClick={() => void handleNewAsset(asset)}>
              {actionLabel}
            </Button>
          </div>
        </div>
      ) : (
        <div className="text-[11px] text-gray-500">当前镜头已关联</div>
      )
    return (
      <div key={`${asset.kind}:${asset.name}`} className="col-span-12 md:col-span-6 xl:col-span-3 2xl:col-span-2">
        <DisplayImageCard
          title={
            <div className="flex items-center justify-between gap-2 min-w-0">
              <div className="min-w-0">
                {asset.id ? (
                  <Button
                    type="link"
                    size="small"
                    className="!p-0 !h-auto"
                    onClick={() =>
                      window.open(assetDetailUrl(asset.kind, asset.id!, projectId ?? ''), '_blank', 'noopener,noreferrer')
                    }
                  >
                    <span className="truncate inline-block max-w-[140px] align-bottom">{asset.name}</span>
                  </Button>
                ) : (
                  <Tooltip title="该资产仅提取结果，尚未落库">
                    <span className="truncate inline-block max-w-[140px] text-gray-400 cursor-not-allowed align-bottom">{asset.name}</span>
                  </Tooltip>
                )}
              </div>
              {asset.status === 'linked' ? <Tag color="blue">已关联</Tag> : <Tag color="magenta">新提取</Tag>}
            </div>
          }
          imageUrl={resolveAssetUrl(asset.thumbnail)}
          imageAlt={asset.name}
          enablePreview
          hoverable={false}
          size="small"
          imageHeightClassName="h-24"
          footer={footer}
        />
      </div>
    )
  }

  const renderAssetGrid = (kind: AssetKind, titleLabel: string, items: AssetVM[]) => {
    const linkedItems = items.filter((item) => item.status === 'linked')
    const candidateItems = items.filter((item) => item.status === 'new')
    const expanded = expandedKinds[kind]
    const linkedVisible = expanded ? linkedItems : linkedItems.slice(0, 6)
    const candidateVisible = expanded ? candidateItems : candidateItems.slice(0, 6)
    const hiddenCount = Math.max(0, linkedItems.length + candidateItems.length - linkedVisible.length - candidateVisible.length)
    return (
      <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/60 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs text-gray-600 font-medium">
            {titleLabel}（{items.length}）
          </div>
          {items.length > 12 ? (
            <Button type="link" size="small" onClick={() => toggleExpanded(kind)}>
              {expanded ? '收起' : `更多（+${hiddenCount}）`}
            </Button>
          ) : null}
        </div>
        {items.length === 0 ? (
          <Empty description={`暂无${titleLabel}`} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div className="space-y-3">
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="text-[11px] font-medium text-slate-600">当前已关联（{linkedItems.length}）</div>
                {linkedItems.length > 0 ? <Tag color="blue">当前状态</Tag> : null}
              </div>
              {linkedItems.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-4 text-xs text-slate-500">
                  当前镜头还没有关联{titleLabel}
                </div>
              ) : (
                <div className="grid grid-cols-12 gap-2">
                  {linkedVisible.map((asset) => renderAssetCard(asset))}
                </div>
              )}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="text-[11px] font-medium text-slate-600">待确认候选（{candidateItems.length}）</div>
                {candidateItems.length > 0 ? <Tag color="magenta">待确认</Tag> : null}
              </div>
              {candidateItems.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-4 text-xs text-slate-500">
                  当前没有待确认的{titleLabel}候选
                </div>
              ) : (
                <div className="grid grid-cols-12 gap-2">
                  {candidateVisible.map((asset) => renderAssetCard(asset))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  if (!projectId || !chapterId || !shotId) {
    return <Navigate to="/projects" replace />
  }

  const hasTitleAndExcerpt = !!title.trim() && !!scriptExcerpt.trim()
  const linkedAssetCount = shotAssetsOverview?.summary.linked_count ?? 0
  const pendingAssetCount = shotAssetsOverview?.summary.pending_count ?? 0
  const assetsReady = pendingAssetCount === 0 && linkedAssetCount > 0
  const dialogsReady = extractedDialogLines.length === 0
  const readyToShoot = hasTitleAndExcerpt && assetsReady && dialogsReady

  const checklistItems = [
    {
      key: 'script',
      label: '标题与摘录',
      tone: hasTitleAndExcerpt ? 'success' : 'warning',
      text: hasTitleAndExcerpt ? '已保存基础信息' : '请先补标题和剧本摘录',
    },
    {
      key: 'assets',
      label: '资产',
      tone: assetsReady ? 'success' : shotAssetsOverview ? 'warning' : 'default',
      text: assetsReady ? '关联资产已确认' : shotAssetsOverview ? `还有 ${pendingAssetCount} 项待处理` : '建议先提取并确认资产',
    },
    {
      key: 'dialogs',
      label: '对白',
      tone: dialogsReady ? 'success' : extractedDialogLines.length > 0 ? 'warning' : 'default',
      text: dialogsReady
        ? savedDialogLines.length > 0
          ? '对白已确认'
          : '当前镜头无对白，可继续后续流程'
        : extractedDialogLines.length > 0
          ? `有 ${extractedDialogLines.length} 条待确认`
          : '可继续提取或补录对白',
    },
    {
      key: 'shoot',
      label: '拍摄准备',
      tone: readyToShoot ? 'success' : 'default',
      text: readyToShoot ? '当前镜头可进入拍摄' : '请先补齐上面 3 项',
    },
  ] as const

  return (
    <Layout style={{ height: '100%', minHeight: 0, background: '#eef2f7' }}>
      <Header
        style={{
          padding: '0 16px',
          background: '#fff',
          borderBottom: '1px solid #e2e8f0',
          boxShadow: '0 2px 4px rgba(0,0,0,0.04)',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}
      >
        <Link
          to={getChapterShotsPath(projectId, chapterId)}
          className="text-gray-600 hover:text-blue-600 flex items-center gap-1"
        >
          <ArrowLeftOutlined /> 返回分镜列表
        </Link>
        <Divider type="vertical" />

        <div className="min-w-0 flex-1 overflow-hidden">
          <Typography.Text
            strong
            className="truncate block"
            style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          >
            {chapterIndex !== null ? `第${chapterIndex}章 · ${chapterTitle || '未命名'}` : chapterTitle || '章节'}
          </Typography.Text>
          <Typography.Text
            type="secondary"
            className="text-xs truncate block"
            style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          >
            编辑分镜
          </Typography.Text>
        </div>
      </Header>

      <Content
        style={{
          padding: 16,
          minHeight: 0,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Card
          title="分镜编辑"
          style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
          bodyStyle={{
            padding: 12,
            flex: 1,
            minHeight: 0,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {loading ? (
            <div className="flex-1 flex items-center justify-center min-h-[200px]">
              <Spin size="large" />
            </div>
          ) : !shot ? (
            <Empty description="无法加载分镜" />
          ) : (
            <div style={{ flex: 1, minHeight: 0, display: 'flex', gap: 12, overflow: 'hidden' }}>
              <Card
                size="small"
                title={`镜头（${shotsSorted.length}）`}
                style={{
                  width: 320,
                  minWidth: 260,
                  maxWidth: 420,
                  height: '100%',
                  minHeight: 0,
                  overflow: 'hidden',
                  display: 'flex',
                  flexDirection: 'column',
                }}
                bodyStyle={{ padding: 8, flex: 1, minHeight: 0, overflow: 'auto' }}
              >
                <List
                  size="small"
                  dataSource={shotsSorted}
                  locale={{ emptyText: <Empty description="暂无镜头" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                  renderItem={(item) => {
                    const active = item.id === shotId
                    return (
                      <List.Item
                        onClick={() => goShot(item.id)}
                        style={{
                          cursor: 'pointer',
                          borderRadius: 10,
                          padding: '8px 10px',
                          background: active ? 'rgba(59,130,246,0.10)' : undefined,
                        }}
                      >
                        <div className="min-w-0">
                          <div className="font-medium truncate">
                            #{item.index} · {item.title?.trim() ? item.title : '未命名镜头'}
                          </div>
                          <div className="text-xs text-gray-500 truncate">{item.script_excerpt ?? ''}</div>
                        </div>
                      </List.Item>
                    )
                  }}
                />
              </Card>

              <Card
                size="small"
                title={
                  <div className="space-y-3 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 min-w-0">
                      <span className="shrink-0">{`镜头 #${shot.index} 详情`}</span>
                      <Input
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        placeholder="标题"
                        size="small"
                        style={{ maxWidth: 520, flex: '1 1 200px' }}
                      />
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {checklistItems.map((item) => (
                        <div
                          key={item.key}
                          className="rounded-xl border px-3 py-2 bg-white/70 min-w-[180px] flex-1"
                          style={{
                            borderColor:
                              item.tone === 'success'
                                ? '#86efac'
                                : item.tone === 'warning'
                                  ? '#fcd34d'
                                  : '#dbeafe',
                            background:
                              item.tone === 'success'
                                ? '#f0fdf4'
                                : item.tone === 'warning'
                                  ? '#fffbeb'
                                  : '#f8fafc',
                          }}
                        >
                          <div className="text-[11px] text-gray-500 mb-1">{item.label}</div>
                          <div className="text-sm font-medium text-gray-900">{item.text}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                }
                style={{
                  flex: 1,
                  minWidth: 0,
                  height: '100%',
                  minHeight: 0,
                  overflow: 'hidden',
                  display: 'flex',
                  flexDirection: 'column',
                }}
                bodyStyle={{ padding: 12, flex: 1, minHeight: 0, overflow: 'auto' }}
              >
                <div className="space-y-3">
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <div className="text-xs text-gray-600">剧本摘录</div>
                      <Button
                        type="primary"
                        size="small"
                        icon={<SaveOutlined />}
                        loading={saving}
                        onClick={() => void saveShot()}
                      >
                        保存
                      </Button>
                    </div>
                    <Input.TextArea
                      value={scriptExcerpt}
                      onChange={(e) => setScriptExcerpt(e.target.value)}
                      autoSize={{ minRows: 4, maxRows: 14 }}
                      placeholder="剧本摘录"
                    />
                  </div>

                  <Divider className="!my-2" />
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="text-xs text-gray-600 font-medium">关联资产</div>
                      <div className="flex items-center gap-2">
                        <Button
                          type="primary"
                          size="small"
                          loading={extractingAssets}
                          onClick={() => void extractAssets()}
                        >
                          提取资产
                        </Button>
                        {shot?.skip_extraction ? (
                          <Button
                            size="small"
                            loading={skipExtractionUpdating}
                            onClick={() => void updateSkipExtraction(false)}
                          >
                            恢复提取
                          </Button>
                        ) : (
                          <Popconfirm
                            title="确认标记为无需提取？"
                            description="标记后当前镜头会直接按“提取确认已完成”处理。"
                            okText="确认"
                            cancelText="取消"
                            onConfirm={() => void updateSkipExtraction(true)}
                            okButtonProps={{ danger: true, loading: skipExtractionUpdating }}
                            cancelButtonProps={{ disabled: skipExtractionUpdating }}
                          >
                            <Button
                              size="small"
                              danger
                              loading={skipExtractionUpdating}
                            >
                              无需提取
                            </Button>
                          </Popconfirm>
                        )}
                      </div>
                    </div>
                    {shot?.skip_extraction ? (
                      <div className="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
                        当前镜头已标记为无需提取，系统会直接按“提取确认已完成”处理。
                      </div>
                    ) : null}
                    <div className="space-y-4">
                      {renderAssetGrid('scene', '场景', unionAssets.scene)}
                      {renderAssetGrid('actor', '角色', unionAssets.actor)}
                      {renderAssetGrid('prop', '道具', unionAssets.prop)}
                      {renderAssetGrid('costume', '服装', unionAssets.costume)}
                    </div>
                  </div>

                  <Divider className="!my-2" />
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="text-xs text-gray-600 font-medium">对白</div>
                      <div className="flex items-center gap-2">
                        {extractedDialogLines.length > 0 ? (
                          <>
                            <Button size="small" loading={batchDialogAdding} onClick={() => void acceptAllExtractedDialogLines()}>
                              全部接受
                            </Button>
                            <Button size="small" disabled={batchDialogAdding} onClick={ignoreAllExtractedDialogLines}>
                              全部忽略
                            </Button>
                          </>
                        ) : null}
                        {dialogLoading ? <Spin size="small" /> : null}
                      </div>
                    </div>

                    <div className="space-y-2">
                      {savedDialogLines.length === 0 && extractedDialogLines.length === 0 ? (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无对白" />
                      ) : null}

                      {savedDialogLines.length > 0 ? (
                        <div className="space-y-2">
                          {savedDialogLines
                            .slice()
                            .sort((a, b) => (a.index ?? 0) - (b.index ?? 0))
                            .map((l) => (
                              <div key={l.id} className="flex items-start gap-2">
                                <Tooltip title="已保存">
                                  <span className="mt-1 text-gray-500">
                                    <SmileOutlined />
                                  </span>
                                </Tooltip>
                                <Button
                                  type="text"
                                  size="small"
                                  danger
                                  icon={<DeleteOutlined />}
                                  loading={!!dialogDeletingIds[l.id]}
                                  onClick={() => void deleteSavedDialogLine(l.id)}
                                />
                                <div className="w-36 shrink-0 text-xs text-gray-700 mt-1 truncate">
                                  {dialogTitle(l.speaker_name, l.target_name)}
                                </div>
                                <Input.TextArea
                                  value={l.text ?? ''}
                                  onChange={(e) => updateSavedDialogText(l.id, e.target.value)}
                                  autoSize={{ minRows: 1, maxRows: 4 }}
                                  placeholder="对白内容"
                                  status={dialogSavingIds[l.id] ? 'warning' : undefined}
                                />
                              </div>
                            ))}
                        </div>
                      ) : null}

                      {extractedDialogLines.length > 0 ? (
                        <div className="space-y-2">
                          {extractedDialogLines.map((l) => (
                            <div key={l.__key} className="flex items-start gap-2">
                              <Tooltip title="新提取">
                                <span className="mt-1 text-red-600">
                                  <FireOutlined />
                                </span>
                              </Tooltip>
                              <Button
                                type="text"
                                size="small"
                                icon={<PlusOutlined />}
                                loading={!!dialogAddingKeys[l.__key]}
                                onClick={() => void addExtractedDialogLine(l)}
                              />
                              <div className="w-36 shrink-0 text-xs text-gray-700 mt-1 truncate">
                                {dialogTitle(l.speaker_name, l.target_name)}
                              </div>
                              <Input.TextArea
                                value={l.text ?? ''}
                                onChange={(e) => updateExtractedDialogText(l.__key, e.target.value)}
                                autoSize={{ minRows: 1, maxRows: 4 }}
                                placeholder="对白内容"
                              />
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
              </Card>
            </div>
          )}
        </Card>
      </Content>

      <Modal
        title="关联资产"
        open={linkingOpen}
        onCancel={() => setLinkingOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setLinkingOpen(false)} disabled={linkingActionLoading}>
            取消
          </Button>,
          <Button
            key="link"
            type="primary"
            loading={linkingActionLoading}
            disabled={!linkingItem?.asset_id}
            onClick={() => void doLink()}
          >
            关联
          </Button>,
        ]}
        width={520}
      >
        <div className="space-y-3">
          <Typography.Text>{linkingHint}</Typography.Text>
          <DisplayImageCard
            title={<div className="truncate">{linkingName || '—'}</div>}
            imageAlt={linkingName || 'asset'}
            imageUrl={linkingThumb}
            placeholder={linkingLoading ? <Spin /> : '暂无图片'}
            enablePreview
            hoverable={false}
            size="small"
            imageHeightClassName="h-44"
          />
        </div>
      </Modal>
    </Layout>
  )
}
