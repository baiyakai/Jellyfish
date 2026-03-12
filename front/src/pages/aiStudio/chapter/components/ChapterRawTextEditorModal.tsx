import React, { useEffect, useMemo, useState } from 'react'
import { Button, Collapse, Input, Modal, Space, Spin, Tag, message } from 'antd'
import {
  DiffOutlined,
  FileTextOutlined,
  HistoryOutlined,
  ReloadOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { StudioChaptersService } from '../../../../services/generated'

type EditorMode = 'raw' | 'condensed' | 'compare'

type HistoryItem = {
  id: string
  at: number
  rawText: string
  condensedText: string
}

export function ChapterRawTextEditorModal({
  open,
  onClose,
  chapterId,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  chapterId: string | undefined
  onSaved?: (next: { rawText?: string; condensedText?: string }) => void
}) {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)

  const [mode, setMode] = useState<EditorMode>('raw')
  const [rawText, setRawText] = useState('')
  const [condensedText, setCondensedText] = useState('')
  const [editorText, setEditorText] = useState('')
  const [compareRaw, setCompareRaw] = useState('')
  const [compareCondensed, setCompareCondensed] = useState('')

  const plainWordCount = useMemo(() => editorText.trim().length, [editorText])
  const paragraphCount = useMemo(() => editorText.split(/\n\s*\n/).filter((p) => p.trim()).length, [editorText])

  useEffect(() => {
    if (!open) return
    if (!chapterId) return
    setLoading(true)
    StudioChaptersService.getChapterApiV1StudioChaptersChapterIdGet({ chapterId })
      .then((res) => {
        const data = res.data
        const nextRaw = data?.raw_text ?? ''
        const nextCondensed = data?.condensed_text ?? ''
        setRawText(nextRaw)
        setCondensedText(nextCondensed)
        setMode('raw')
        setEditorText(nextRaw)
        setCompareRaw(nextRaw)
        setCompareCondensed(nextCondensed)
      })
      .catch(() => {
        message.error('加载章节失败')
      })
      .finally(() => setLoading(false))
  }, [open, chapterId])

  const handleSmartSimplify = async () => {
    if (!rawText.trim()) {
      message.warning('请先输入原文')
      return
    }
    setExtracting(true)
    try {
      // TODO: 智能精简接口未接入，后续在此替换为真实接口调用，并将返回结果写入 condensedText
      await new Promise((r) => setTimeout(r, 500))
      const simplified = '已精简'
      setCondensedText(simplified)
      if (mode === 'compare') {
        // 对比模式下不切换编辑区：只更新右侧精简内容输入框
        setCompareCondensed(simplified)
      } else {
        setMode('condensed')
        setEditorText(simplified)
      }
      message.success('智能精简完成')
    } finally {
      setExtracting(false)
    }
  }

  const handleBackToRaw = () => {
    setMode('raw')
    setEditorText(rawText)
  }

  const handleViewCondensed = () => {
    if (!condensedText.trim()) {
      message.info('暂无精简内容')
      return
    }
    setMode('condensed')
    setEditorText(condensedText)
  }

  const handleSave = async () => {
    if (!chapterId) return
    setSaving(true)
    try {
      if (mode === 'raw') {
        await StudioChaptersService.updateChapterApiV1StudioChaptersChapterIdPatch({
          chapterId,
          requestBody: { raw_text: editorText },
        })
        setRawText(editorText)
        onSaved?.({ rawText: editorText })
        message.success('原文已保存')
        return
      }

      if (mode === 'condensed') {
        await StudioChaptersService.updateChapterApiV1StudioChaptersChapterIdPatch({
          chapterId,
          requestBody: { condensed_text: editorText },
        })
        setCondensedText(editorText)
        onSaved?.({ condensedText: editorText })
        message.success('精简内容已保存')
        return
      }

      await StudioChaptersService.updateChapterApiV1StudioChaptersChapterIdPatch({
        chapterId,
        requestBody: { raw_text: compareRaw, condensed_text: compareCondensed },
      })
      setRawText(compareRaw)
      setCondensedText(compareCondensed)
      onSaved?.({ rawText: compareRaw, condensedText: compareCondensed })
      message.success('已保存')
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const mockHistory: HistoryItem[] = useMemo(
    () => [
      {
        id: 'h-1',
        at: Date.now() - 1000 * 60 * 60 * 2,
        rawText: '【原文】示例版本 1（预置数据）',
        condensedText: '【精简】示例版本 1（预置数据）',
      },
      {
        id: 'h-2',
        at: Date.now() - 1000 * 60 * 22,
        rawText: '【原文】示例版本 2（预置数据）',
        condensedText: '【精简】示例版本 2（预置数据）',
      },
    ],
    [],
  )

  return (
    <>
      <Modal
        title={
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              <FileTextOutlined />{' '}
              {mode === 'raw' ? '原文编辑区' : mode === 'condensed' ? '精简内容编辑区' : '对比模式'}
              <Tag color="blue">{plainWordCount} 字</Tag>
              <Tag color="default">{paragraphCount} 段</Tag>
            </div>
            <Space size="small">
              <Button size="small" type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => void handleSave()}>
                保存
              </Button>
              <Button
                size="small"
                icon={<ThunderboltOutlined />}
                loading={extracting}
                onClick={() => void handleSmartSimplify()}
              >
                智能精简
              </Button>
              {mode === 'condensed' ? (
                <Button size="small" icon={<ReloadOutlined />} onClick={handleBackToRaw}>
                  回到原文
                </Button>
              ) : (
                <Button
                  size="small"
                  icon={<ReloadOutlined />}
                  disabled={!condensedText.trim()}
                  onClick={handleViewCondensed}
                >
                  查看精简
                </Button>
              )}
              <Button
                size="small"
                icon={<DiffOutlined />}
                type={mode === 'compare' ? 'primary' : 'default'}
                onClick={() => {
                  if (mode === 'compare') {
                    setMode('raw')
                    setEditorText(rawText)
                    return
                  }
                  setCompareRaw(rawText)
                  setCompareCondensed(condensedText)
                  setMode('compare')
                }}
              >
                对比模式
              </Button>
              <Button size="small" icon={<HistoryOutlined />} onClick={() => setHistoryOpen(true)}>
                版本历史
              </Button>
            </Space>
          </div>
        }
        open={open}
        onCancel={onClose}
        width={900}
        footer={
          <Button type="primary" onClick={onClose}>
            关闭
          </Button>
        }
        styles={{ body: { maxHeight: '70vh', overflow: 'auto', paddingTop: 12 } }}
      >
        {loading ? (
          <div className="flex justify-center items-center py-10">
            <Spin />
          </div>
        ) : mode === 'compare' ? (
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col">
              <div className="text-xs text-gray-500 mb-2">原文</div>
              <Input.TextArea
                value={compareRaw}
                onChange={(e) => setCompareRaw(e.target.value)}
                rows={14}
                style={{ resize: 'none', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}
              />
            </div>
            <div className="flex flex-col">
              <div className="text-xs text-gray-500 mb-2">精简内容</div>
              <Input.TextArea
                value={compareCondensed}
                onChange={(e) => setCompareCondensed(e.target.value)}
                rows={14}
                style={{ resize: 'none', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}
              />
            </div>
          </div>
        ) : (
          <Input.TextArea
            value={editorText}
            onChange={(e) => {
              const v = e.target.value
              setEditorText(v)
              if (mode === 'raw') setRawText(v)
              if (mode === 'condensed') setCondensedText(v)
            }}
            placeholder={mode === 'raw' ? '编辑章节原文…' : '编辑精简内容…'}
            rows={16}
            style={{ resize: 'none', background: '#fdfdfd' }}
          />
        )}
      </Modal>

      <Modal
        title={
          <div className="flex items-center gap-2">
            <HistoryOutlined /> 历史版本
          </div>
        }
        open={historyOpen}
        onCancel={() => setHistoryOpen(false)}
        width={920}
        footer={
          <Button type="primary" onClick={() => setHistoryOpen(false)}>
            关闭
          </Button>
        }
        styles={{ body: { maxHeight: '70vh', overflow: 'auto' } }}
      >
        {/* TODO: 历史版本接口未接入，当前为预置数据；后续接入后按时间线渲染即可 */}
        <div className="text-xs text-gray-500 mb-3">内容默认折叠，仅展示时间线节点。</div>
        <div className="space-y-3">
          {mockHistory.map((h) => (
            <div key={h.id} className="border border-gray-200 rounded-lg p-3 bg-white">
              <div className="text-sm font-medium mb-2">{new Date(h.at).toLocaleString()}</div>
              <Collapse
                items={[
                  {
                    key: 'content',
                    label: '展开查看内容',
                    children: (
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <div className="text-xs text-gray-500 mb-2">原文内容</div>
                          <Input.TextArea
                            value={h.rawText}
                            readOnly
                            rows={8}
                            style={{ resize: 'none', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}
                          />
                        </div>
                        <div>
                          <div className="text-xs text-gray-500 mb-2">精简内容</div>
                          <Input.TextArea
                            value={h.condensedText}
                            readOnly
                            rows={8}
                            style={{ resize: 'none', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}
                          />
                        </div>
                      </div>
                    ),
                  },
                ]}
              />
            </div>
          ))}
        </div>
      </Modal>
    </>
  )
}

