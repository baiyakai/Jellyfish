import { useEffect, useMemo, useState } from 'react'
import { Card, Input, InputNumber, Row, Col, Tag, Button, message, Modal, Space, Pagination } from 'antd'
import { EditOutlined, DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import { resolveAssetUrl } from '../utils'
import { DisplayImageCard } from '../components/DisplayImageCard'
import { PROJECT_STYLE_OPTIONS_BY_VISUAL, ProjectVisualStyleAndStyleFields } from '../../project/ProjectVisualStyleAndStyleFields'

function normalizeTags(input: string): string[] {
  return input
    .split(/[,，\n]/g)
    .map((t) => t.trim())
    .filter(Boolean)
}

export type StudioAssetLike = {
  id: string
  name: string
  description?: string
  thumbnail?: string
  tags?: string[]
  view_count?: number
}

function normalizeAsset(asset: StudioAssetLike): StudioAssetLike {
  return {
    ...asset,
    // 保持原始 thumbnail 字段来源为接口返回的 item.thumbnail
    // 渲染时再统一在 resolveAssetUrl 里做 URL/file_id 适配
    thumbnail: asset.thumbnail,
  }
}

function clampViewCount(value: number | null): number | null {
  if (value === null) return null
  return Math.max(0, Math.min(4, Math.trunc(value)))
}

type AssetMutationPayload = Record<string, unknown> & {
  name: string
  description?: string
  tags?: string[]
  view_count?: number | null
  thumbnail?: string
}

type AssetCreatePayload = Record<string, unknown> & {
  name: string
  thumbnail?: string
}

export function AssetTypeTab({
  label,
  tabKey,
  listAssets,
  createAsset,
  updateAsset,
  deleteAsset,
  onEditAsset,
}: {
  label: string
  tabKey: 'scene' | 'prop' | 'costume'
  listAssets: (params: { q?: string; page: number; pageSize: number }) => Promise<{ items: StudioAssetLike[]; total: number }>
  createAsset: (payload: AssetCreatePayload) => Promise<StudioAssetLike>
  updateAsset: (id: string, payload: AssetMutationPayload) => Promise<StudioAssetLike>
  deleteAsset: (id: string) => Promise<void>
  onEditAsset?: (asset: StudioAssetLike) => void
}) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [assets, setAssets] = useState<StudioAssetLike[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(12)
  const [total, setTotal] = useState(0)

  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<StudioAssetLike | null>(null)
  const [formName, setFormName] = useState('')
  const [formDesc, setFormDesc] = useState('')
  const [formTags, setFormTags] = useState('')
  const [formViewCount, setFormViewCount] = useState<number | null>(null)
  const [formVisualStyle, setFormVisualStyle] = useState<'现实' | '动漫'>('现实')
  const [formStyle, setFormStyle] = useState<string>(PROJECT_STYLE_OPTIONS_BY_VISUAL['现实'][0]?.value ?? '真人都市')

  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewUrl, setPreviewUrl] = useState('')
  const [previewTitle, setPreviewTitle] = useState('')

  const load = async (opts?: { page?: number; pageSize?: number; q?: string }) => {
    setLoading(true)
    try {
      const nextPage = opts?.page ?? page
      const nextPageSize = opts?.pageSize ?? pageSize
      const nextQ = typeof opts?.q === 'string' ? opts.q : search.trim() || undefined
      const res = await listAssets({ q: nextQ, page: nextPage, pageSize: nextPageSize })
      const items = Array.isArray(res.items) ? res.items.map(normalizeAsset) : []
      setAssets(items)
      setTotal(res.total)
    } catch {
      message.error('加载资产失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize])

  const filtered = useMemo(() => {
    return Array.isArray(assets) ? assets : []
  }, [assets])

  const openCreate = () => {
    setEditing(null)
    setFormName('')
    setFormDesc('')
    setFormTags('')
    setFormViewCount(null)
    setFormVisualStyle('现实')
    setFormStyle(PROJECT_STYLE_OPTIONS_BY_VISUAL['现实'][0]?.value ?? '真人都市')
    setEditOpen(true)
  }

  useEffect(() => {
    const create = searchParams.get('create')
    const name = searchParams.get('name') ?? ''
    const desc = searchParams.get('desc') ?? ''
    const tab = searchParams.get('tab')
    if (create === '1' && tab === tabKey) {
      setEditing(null)
      setFormName(name)
      setFormDesc(desc)
      setFormTags('')
      setFormViewCount(null)
      setFormVisualStyle('现实')
      setFormStyle(PROJECT_STYLE_OPTIONS_BY_VISUAL['现实'][0]?.value ?? '真人都市')
      setEditOpen(true)
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.delete('create')
          next.delete('name')
          next.delete('desc')
          return next
        },
        { replace: true },
      )
    }
  }, [searchParams, setSearchParams, tabKey])

  const openEdit = (asset: StudioAssetLike) => {
    setEditing(asset)
    setFormName(asset.name)
    setFormDesc(asset.description ?? '')
    setFormTags((asset.tags ?? []).join(', '))
    setFormViewCount(asset.view_count ?? null)
    const nextVisual = (((asset as any).visual_style as '现实' | '动漫' | undefined) ?? '现实') as '现实' | '动漫'
    setFormVisualStyle(nextVisual)
    setFormStyle(((asset as any).style as string | undefined) ?? PROJECT_STYLE_OPTIONS_BY_VISUAL[nextVisual]?.[0]?.value ?? '真人都市')
    setEditOpen(true)
  }

  const handleEdit = (asset: StudioAssetLike) => {
    if (onEditAsset) {
      onEditAsset(asset)
      return
    }
    openEdit(asset)
  }

  const handleSave = async () => {
    if (!formName.trim()) {
      message.warning('请输入资产名称')
      return
    }

    try {
      const nextViewCount = clampViewCount(formViewCount)

      if (editing) {
        const next = await updateAsset(editing.id, {
          name: formName.trim(),
          description: formDesc.trim(),
          tags: normalizeTags(formTags),
          view_count: nextViewCount,
          visual_style: formVisualStyle,
          style: formStyle,
        })
        const normalizedNext = normalizeAsset(next)
        setAssets((prev) => prev.map((a) => (a.id === editing.id ? normalizedNext : a)))
        message.success('已保存')
      } else {
        await createAsset({
          id: `asset_${Date.now()}`,
          name: formName.trim(),
          description: formDesc.trim(),
          tags: normalizeTags(formTags),
          thumbnail: '',
          visual_style: formVisualStyle,
          style: formStyle,
          ...(nextViewCount === null ? {} : { view_count: nextViewCount }),
        })
        message.success('已创建')
        // 创建后回到第一页刷新，保证立刻可见（服务端可能按时间倒序）
        setPage(1)
        await load({ page: 1 })
      }
      setEditOpen(false)
      setEditing(null)
      if (editing) {
        await load()
      }
    } catch {
      message.error('保存失败')
    }
  }

  const handleDelete = (asset: StudioAssetLike) => {
    Modal.confirm({
      title: `删除${label}资产？`,
      content: `将删除「${asset.name}」。`,
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteAsset(asset.id)
          message.success('已删除')
          await load()
        } catch {
          message.error('删除失败')
        }
      },
    })
  }

  const openPreview = (asset: StudioAssetLike) => {
    const thumbnailUrl = resolveAssetUrl(asset.thumbnail)
    if (!thumbnailUrl) {
      message.info('未生成图片')
      return
    }
    setPreviewTitle(asset.name)
    setPreviewUrl(thumbnailUrl)
    setPreviewOpen(true)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Input.Search
          placeholder={`搜索${label}名称、描述或标签`}
          allowClear
          className="max-w-sm"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onSearch={() => {
            setPage(1)
            void load()
          }}
        />
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建{label}
          </Button>
        </Space>
      </div>

      <Card loading={loading}>
        <Row gutter={[16, 16]}>
          {filtered.length === 0 ? (
            <Col span={24}>
              <div className="text-center text-gray-500 py-8">{search ? '无匹配资产' : '暂无该类资产'}</div>
            </Col>
          ) : (
            filtered.map((a) => {
              const thumbnailUrl = resolveAssetUrl(a.thumbnail)
              return (
              <Col xs={24} sm={12} md={8} lg={6} key={a.id}>
                <DisplayImageCard
                  title={<span className="truncate">{a.name}</span>}
                  imageUrl={thumbnailUrl}
                  imageAlt={a.name}
                  placeholder="未生成"
                  onImageClick={() => openPreview(a)}
                  extra={
                    <Space size="small">
                      <Button size="small" type="link" icon={<EditOutlined />} onClick={() => handleEdit(a)}>
                        编辑
                      </Button>
                    </Space>
                  }
                  actions={[
                    <Button
                      type="text"
                      key="del"
                      danger
                      icon={<DeleteOutlined />}
                      size="small"
                      onClick={() => handleDelete(a)}
                    />,
                  ]}
                  meta={
                    <>
                      <div className="text-xs text-gray-500 mb-2 line-clamp-2">{a.description || '暂无描述'}</div>
                      <div className="flex flex-wrap gap-1">
                        {typeof a.view_count === 'number' && <Tag color="blue">镜头 {a.view_count}</Tag>}
                        {(a.tags ?? []).slice(0, 3).map((t) => (
                          <Tag key={t}>{t}</Tag>
                        ))}
                      </div>
                    </>
                  }
                />
              </Col>
            )})
          )}
        </Row>

        <div className="flex justify-end pt-4">
          <Pagination
            current={page}
            pageSize={pageSize}
            total={total}
            showSizeChanger={false}
            showTotal={(t) => `共 ${t} 条`}
            onChange={(p, ps) => {
              setPage(p)
              setPageSize(ps)
            }}
          />
        </div>
      </Card>

      <Modal
        title={editing ? `编辑${label}` : `新建${label}`}
        open={editOpen}
        onCancel={() => {
          setEditOpen(false)
          setEditing(null)
        }}
        onOk={handleSave}
        okText="保存"
        width={560}
      >
        <div className="space-y-3">
          <div>
            <span className="text-gray-600 text-sm">名称</span>
            <Input value={formName} onChange={(e) => setFormName(e.target.value)} className="mt-1" />
          </div>
          <div>
            <span className="text-gray-600 text-sm">描述</span>
            <Input.TextArea value={formDesc} onChange={(e) => setFormDesc(e.target.value)} rows={4} className="mt-1" />
          </div>
          <div>
            <span className="text-gray-600 text-sm">标签（逗号分隔）</span>
            <Input value={formTags} onChange={(e) => setFormTags(e.target.value)} className="mt-1" />
          </div>
          <div>
            <span className="text-gray-600 text-sm">镜头数</span>
            <InputNumber
              min={0}
              max={4}
              precision={0}
              value={formViewCount}
              onChange={(v) => setFormViewCount(v ?? null)}
              className="mt-1 w-full"
              placeholder="例如 4（最大 4）"
            />
          </div>
          <div>
            <ProjectVisualStyleAndStyleFields
              visual_style={formVisualStyle}
              style={formStyle}
              onChange={(next) => {
                setFormVisualStyle(next.visual_style)
                setFormStyle(next.style)
              }}
            />
          </div>
        </div>
      </Modal>

      <Modal
        title={previewTitle}
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        footer={null}
        width={880}
      >
        <div className="w-full flex justify-center bg-gray-50 rounded-md overflow-hidden">
          {/* 预览不做 image 组件依赖，直接 img */}
          <img src={previewUrl} alt={previewTitle} className="max-h-[70vh] object-contain" />
        </div>
      </Modal>
    </div>
  )
}

