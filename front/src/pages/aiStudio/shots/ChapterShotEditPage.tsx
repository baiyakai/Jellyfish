import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Divider, Empty, Input, Layout, List, Modal, Spin, Tag, Tooltip, Typography, message } from 'antd'
import { ArrowLeftOutlined, DeleteOutlined, FireOutlined, PlusOutlined, SaveOutlined, SmileOutlined } from '@ant-design/icons'
import type {
  EntityNameExistenceItem,
  ShotDialogLineCreate,
  ShotDialogLineRead,
  ShotDialogLineUpdate,
  ShotRead,
  StudioAssetDraft,
  StudioCharacterDraft,
  StudioScriptExtractionDraft,
  StudioShotDraftDialogueLine,
} from '../../../services/generated'
import {
  ScriptProcessingService,
  StudioChaptersService,
  StudioEntitiesService,
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
type AssetVM = NamedDraft & { kind: AssetKind; status: 'linked' | 'new' }
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

function normalizeName(name: string) {
  return name.trim()
}

function uniqByName<T extends { name: string }>(items: T[]) {
  const seen = new Set<string>()
  const out: T[] = []
  for (const it of items) {
    const key = normalizeName(it.name)
    if (!key) continue
    if (seen.has(key)) continue
    seen.add(key)
    out.push({ ...it, name: key })
  }
  return out
}

function buildUnionVM(kind: AssetKind, linked: NamedDraft[], aux: NamedDraft[]): AssetVM[] {
  const linkedMap = new Set(linked.map((x) => normalizeName(x.name)).filter(Boolean))
  const auxMap = new Set(aux.map((x) => normalizeName(x.name)).filter(Boolean))
  const union = uniqByName([...linked, ...aux]).map((x) => {
    const key = normalizeName(x.name)
    const status: AssetVM['status'] = linkedMap.has(key) ? 'linked' : auxMap.has(key) ? 'new' : 'new'
    return { ...x, kind, status }
  })
  return union
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
  const [shots, setShots] = useState<ShotRead[]>([])
  const [shot, setShot] = useState<ShotRead | null>(null)
  const [title, setTitle] = useState('')
  const [scriptExcerpt, setScriptExcerpt] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [extractionDraft, setExtractionDraft] = useState<StudioScriptExtractionDraft | null>(null)
  const [extractedAux, setExtractedAux] = useState<StudioScriptExtractionDraft | null>(null)
  const [extractingAssets, setExtractingAssets] = useState(false)
  const extractInFlightRef = useRef(false)

  const pollTimerRef = useRef<number | null>(null)
  const pollInFlightRef = useRef(false)
  const [pollEnabled, setPollEnabled] = useState(false)

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
  const dialogDebounceTimersRef = useRef<Map<number, number>>(new Map())

  const shotsSorted = useMemo(
    () => [...shots].sort((a, b) => a.index - b.index),
    [shots],
  )

  const linkedFromDraft = useMemo(() => {
    const characters = (extractionDraft?.characters ?? []) as StudioCharacterDraft[]
    const scenes = (extractionDraft?.scenes ?? []) as StudioAssetDraft[]
    const props = (extractionDraft?.props ?? []) as StudioAssetDraft[]
    const costumes = (extractionDraft?.costumes ?? []) as StudioAssetDraft[]
    return {
      actor: uniqByName(characters.map((c) => ({ name: c.name, thumbnail: c.thumbnail ?? null, id: c.id ?? null, file_id: c.file_id ?? null, description: c.description ?? null }))),
      scene: uniqByName(scenes.map((s) => ({ name: s.name, thumbnail: s.thumbnail ?? null, id: s.id ?? null, file_id: s.file_id ?? null, description: s.description ?? null }))),
      prop: uniqByName(props.map((p) => ({ name: p.name, thumbnail: p.thumbnail ?? null, id: p.id ?? null, file_id: p.file_id ?? null, description: p.description ?? null }))),
      costume: uniqByName(costumes.map((c) => ({ name: c.name, thumbnail: c.thumbnail ?? null, id: c.id ?? null, file_id: c.file_id ?? null, description: c.description ?? null }))),
    }
  }, [extractionDraft])

  const auxFromExtract = useMemo(() => {
    const characters = (extractedAux?.characters ?? []) as StudioCharacterDraft[]
    const scenes = (extractedAux?.scenes ?? []) as StudioAssetDraft[]
    const props = (extractedAux?.props ?? []) as StudioAssetDraft[]
    const costumes = (extractedAux?.costumes ?? []) as StudioAssetDraft[]
    return {
      actor: uniqByName(characters.map((c) => ({ name: c.name, thumbnail: c.thumbnail ?? null, id: c.id ?? null, file_id: c.file_id ?? null, description: c.description ?? null }))),
      scene: uniqByName(scenes.map((s) => ({ name: s.name, thumbnail: s.thumbnail ?? null, id: s.id ?? null, file_id: s.file_id ?? null, description: s.description ?? null }))),
      prop: uniqByName(props.map((p) => ({ name: p.name, thumbnail: p.thumbnail ?? null, id: p.id ?? null, file_id: p.file_id ?? null, description: p.description ?? null }))),
      costume: uniqByName(costumes.map((c) => ({ name: c.name, thumbnail: c.thumbnail ?? null, id: c.id ?? null, file_id: c.file_id ?? null, description: c.description ?? null }))),
    }
  }, [extractedAux])

  const unionAssets = useMemo(() => {
    return {
      scene: buildUnionVM('scene', linkedFromDraft.scene, auxFromExtract.scene),
      actor: buildUnionVM('actor', linkedFromDraft.actor, auxFromExtract.actor),
      prop: buildUnionVM('prop', linkedFromDraft.prop, auxFromExtract.prop),
      costume: buildUnionVM('costume', linkedFromDraft.costume, auxFromExtract.costume),
    }
  }, [auxFromExtract, linkedFromDraft])

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
      const [chRes, listRes, shotRes] = await Promise.all([
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
      setExtractionDraft(null)
      setExtractedAux(null)
      setPollEnabled(false)
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

  const addExtractedDialogLine = useCallback(
    async (line: ExtractedDialogLineVM) => {
      if (!shotId) return
      if (dialogAddingKeys[line.__key]) return
      const text = (line.text ?? '').trim()
      if (!text) {
        message.warning('请先填写对白内容')
        return
      }
      setDialogAddingKeys((m) => ({ ...m, [line.__key]: true }))
      try {
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
        const created = res.data
        if (created) {
          setSavedDialogLines((prev) => [...prev, created].sort((a, b) => (a.index ?? 0) - (b.index ?? 0)))
          setExtractedDialogLines((prev) => prev.filter((x) => x.__key !== line.__key))
          message.success('已添加')
        } else {
          message.error(res.message || '添加失败')
        }
      } catch {
        message.error('添加失败')
      } finally {
        setDialogAddingKeys((m) => ({ ...m, [line.__key]: false }))
      }
    },
    [dialogAddingKeys, savedDialogLines, shotId],
  )

  useEffect(() => {
    void loadPage()
  }, [loadPage])

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

  const extractAssets = useCallback(async () => {
    if (!projectId || !chapterId || !shot) return
    if (extractInFlightRef.current) return
    extractInFlightRef.current = true
    setExtractingAssets(true)
    setPollEnabled(true)
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
        } as any,
      })
      const next = res.data
      if (next) {
        setExtractedAux((prev) => {
          if (!prev) return next as any
          return {
            ...prev,
            characters: uniqByName([...(prev.characters ?? []), ...(next.characters ?? [])] as any),
            scenes: uniqByName([...(prev.scenes ?? []), ...(next.scenes ?? [])] as any),
            props: uniqByName([...(prev.props ?? []), ...(next.props ?? [])] as any),
            costumes: uniqByName([...(prev.costumes ?? []), ...(next.costumes ?? [])] as any),
            shots: next.shots ?? prev.shots,
          } as any
        })

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
        message.success('提取完成（仅展示，未入库）')
      } else {
        message.error(res.message || '提取失败')
      }
    } catch {
      message.error('提取失败')
    } finally {
      setExtractingAssets(false)
      extractInFlightRef.current = false
    }
  }, [chapterId, projectId, savedDialogLines, shot])

  const goShot = (id: string) => {
    if (!projectId || !chapterId || id === shotId) return
    navigate(`/projects/${projectId}/chapters/${chapterId}/shots/${id}/edit`)
  }

  const pollExtractionDraft = useCallback(async () => {
    if (!shotId) return
    if (pollInFlightRef.current) return
    pollInFlightRef.current = true
    try {
      const res = await StudioShotsService.getShotExtractionDraftApiV1StudioShotsShotIdExtractionDraftGet({ shotId })
      setExtractionDraft(res.data ?? null)
    } catch {
      // 静默：避免每秒弹 toast；保留上一次状态
    } finally {
      pollInFlightRef.current = false
    }
  }, [shotId])

  // 切换分镜时：停止轮询，但固定拉取一次默认 extraction-draft
  useEffect(() => {
    if (!shotId) return
    if (pollTimerRef.current) window.clearInterval(pollTimerRef.current)
    pollTimerRef.current = null
    pollInFlightRef.current = false
    setPollEnabled(false)
    void pollExtractionDraft()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shotId])

  useEffect(() => {
    if (pollTimerRef.current) window.clearInterval(pollTimerRef.current)
    pollTimerRef.current = null
    pollInFlightRef.current = false
    if (!pollEnabled) return
    if (!shotId) return
    void pollExtractionDraft()
    pollTimerRef.current = window.setInterval(() => void pollExtractionDraft(), 1000)
    return () => {
      if (pollTimerRef.current) window.clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
      pollInFlightRef.current = false
    }
  }, [pollEnabled, pollExtractionDraft, shotId])

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
      setLinkingOpen(false)
    } catch {
      message.error('关联失败')
    } finally {
      setLinkingActionLoading(false)
    }
  }, [chapterId, linkingItem?.asset_id, linkingKind, projectId, shotId])

  const handleNewAsset = useCallback(
    async (asset: AssetVM) => {
      if (!projectId || !shotId) return
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
              if (asset.kind === 'scene' || asset.kind === 'prop' || asset.kind === 'costume') {
                open(`/assets?tab=${asset.kind}&create=1&name=${encodeURIComponent(name)}${asset.description?.trim() ? `&desc=${encodeURIComponent(asset.description.trim())}` : ''}`)
                return
              }
              open(`/projects/${projectId}?tab=roles&create=1&name=${encodeURIComponent(name)}${asset.description?.trim() ? `&desc=${encodeURIComponent(asset.description.trim())}` : ''}`)
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
    [openLinkingModal, projectId, shotId],
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

  const renderAssetGrid = (kind: AssetKind, titleLabel: string, items: AssetVM[]) => {
    const expanded = expandedKinds[kind]
    const visible = expanded ? items : items.slice(0, 12)
    const hiddenCount = Math.max(0, items.length - visible.length)
    return (
      <div className="space-y-2">
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
          <div className="grid grid-cols-12 gap-2">
            {visible.map((a) => {
              const statusTag =
                a.status === 'linked' ? (
                  <Tag color="blue">已关联</Tag>
                ) : (
                  <Tag color="magenta">新提取</Tag>
                )
              const existence = existenceByKindName[a.kind][a.name]
              const actionLabel = existence ? (existence.exists ? '关联' : '新建') : '…'
              const footer =
                a.status === 'new' ? (
                  <div className="flex justify-end">
                    <Button size="small" disabled={!existence} onClick={() => void handleNewAsset(a)}>
                      {actionLabel}
                    </Button>
                  </div>
                ) : null
              return (
                <div key={`${a.kind}:${a.name}`} className="col-span-12 md:col-span-6 xl:col-span-3 2xl:col-span-2">
                  <DisplayImageCard
                    title={
                      <div className="flex items-center justify-between gap-2 min-w-0">
                        <div className="min-w-0">
                          {a.id ? (
                            <Button
                              type="link"
                              size="small"
                              className="!p-0 !h-auto"
                              onClick={() =>
                                window.open(assetDetailUrl(a.kind, a.id!, projectId ?? ''), '_blank', 'noopener,noreferrer')
                              }
                            >
                              <span className="truncate inline-block max-w-[140px] align-bottom">{a.name}</span>
                            </Button>
                          ) : (
                            <Tooltip title="该资产仅提取结果，尚未落库">
                              <span className="truncate inline-block max-w-[140px] text-gray-400 cursor-not-allowed align-bottom">{a.name}</span>
                            </Tooltip>
                          )}
                        </div>
                        {statusTag}
                      </div>
                    }
                    imageUrl={resolveAssetUrl(a.thumbnail)}
                    imageAlt={a.name}
                    enablePreview
                    hoverable={false}
                    size="small"
                    imageHeightClassName="h-24"
                    footer={footer}
                  />
                </div>
              )
            })}
          </div>
        )}
      </div>
    )
  }

  if (!projectId || !chapterId || !shotId) {
    return <Navigate to="/projects" replace />
  }

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
                      <Button size="small" loading={extractingAssets} onClick={() => void extractAssets()}>
                        提取资产
                      </Button>
                    </div>
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
                      {dialogLoading ? <Spin size="small" /> : null}
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
