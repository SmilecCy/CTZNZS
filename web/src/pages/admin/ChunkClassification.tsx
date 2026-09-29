// ============================================================
// 文件：pages/admin/ChunkClassification.tsx
// 用途：Chunk 分类查看页 —— 附属资料按章节归类（LLM 自动分类，纯展示）
// 流程：附属资料 → 语义切片 → LLM 分类到章节 → 自动存入
// ============================================================

import { useEffect, useState, useCallback } from 'react'
import {
  Card,
  Table,
  Tag,
  Button,
  Select,
  message,
  Space,
  Spin,
  Empty,
  Alert,
} from 'antd'
import { ReloadOutlined, ExperimentOutlined, CheckCircleOutlined } from '@ant-design/icons'
import * as adminApi from '../../api/admin'
import type { Course } from '../../types'
import { extractErrorMessage } from '../../api/client'

interface ChunkItem {
  chunk_id: string
  chapter_id: number | null
  chapter_name: string | null
  confidence: number | null
  reasoning: string | null
  is_confirmed: boolean
  text: string | null
}

interface MaterialOption {
  id: number
  source_file: string
}

export default function ChunkClassification() {
  const [courses, setCourses] = useState<Course[]>([])
  const [materials, setMaterials] = useState<MaterialOption[]>([])
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null)
  const [selectedMaterialId, setSelectedMaterialId] = useState<number | null>(null)
  const [chunks, setChunks] = useState<ChunkItem[]>([])
  const [loading, setLoading] = useState(false)
  const [classifying, setClassifying] = useState(false)
  // 标记当前数据是已有分类结果还是空
  const [hasExisting, setHasExisting] = useState(false)

  useEffect(() => {
    adminApi.listAllCourses().then(setCourses).catch(() => {
      message.error('加载课程列表失败')
    })
  }, [])

  useEffect(() => {
    if (selectedCourseId) {
      adminApi
        .listMaterials({ courseId: selectedCourseId, uploadType: 'supplement' })
        .then((mats) => {
          setMaterials(
            mats.map((m) => ({ id: m.id, source_file: m.source_file })),
          )
        })
        .catch(() => {
          message.error('加载资料列表失败')
          setMaterials([])
        })
    } else {
      setMaterials([])
    }
    setSelectedMaterialId(null)
  }, [selectedCourseId])

  const loadChunkClassification = useCallback(
    async (materialId: number) => {
      setLoading(true)
      try {
        const result = await adminApi.getChunkClassification(materialId)
        setChunks(result)
        setHasExisting(result.length > 0)
      } catch (err) {
        message.error(extractErrorMessage(err))
        setChunks([])
        setHasExisting(false)
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  // 选择资料后自动从后端加载已有分类结果
  useEffect(() => {
    if (selectedMaterialId) {
      loadChunkClassification(selectedMaterialId)
    } else {
      setChunks([])
      setHasExisting(false)
    }
  }, [selectedMaterialId, loadChunkClassification])

  const handleClassify = async () => {
    if (!selectedMaterialId) return
    setClassifying(true)
    try {
      const result = await adminApi.classifyChunksToChapters(selectedMaterialId)
      setChunks(result)
      setHasExisting(true)
      message.success(`LLM 分类完成，共 ${result.length} 个切片已自动归入对应章节`)
    } catch (err) {
      message.error(extractErrorMessage(err))
    } finally {
      setClassifying(false)
    }
  }

  const columns = [
    {
      title: 'Chunk ID',
      dataIndex: 'chunk_id',
      key: 'chunk_id',
      width: 120,
      ellipsis: true,
    },
    {
      title: '切片文本',
      dataIndex: 'text',
      key: 'text',
      width: 350,
      render: (text: string | null) => (
        <div
          style={{
            maxHeight: 100,
            overflow: 'auto',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
            fontSize: 13,
          }}
        >
          {text || '无文本'}
        </div>
      ),
    },
    {
      title: '归属章节',
      dataIndex: 'chapter_name',
      key: 'chapter_name',
      width: 160,
      render: (name: string | null, record: ChunkItem) => {
        if (!name && !record.chapter_id) {
          return <Tag color="default">未归类</Tag>
        }
        return (
          <span style={{ fontWeight: 500 }}>
            {name || `章节#${record.chapter_id}`}
          </span>
        )
      },
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 90,
      render: (val: number | null) => {
        if (val === null || val === undefined) {
          return <Tag color="default">—</Tag>
        }
        const color = val >= 0.8 ? 'green' : val >= 0.5 ? 'orange' : 'red'
        return <Tag color={color}>{(val * 100).toFixed(0)}%</Tag>
      },
    },
    {
      title: '推理说明',
      dataIndex: 'reasoning',
      key: 'reasoning',
      width: 240,
      ellipsis: true,
      render: (text: string | null) => (
        <span title={text || ''} style={{ color: '#888', fontSize: 12 }}>
          {text || '—'}
        </span>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="Chunk 分类查看"
        extra={
          <Space>
            <Select
              value={selectedCourseId}
              onChange={(val) => setSelectedCourseId(val)}
              placeholder="选择课程"
              style={{ width: 180 }}
              allowClear
              options={courses.map((c) => ({
                value: c.id,
                label: c.display_name || c.name,
              }))}
            />
            <Select
              value={selectedMaterialId}
              onChange={(val) => setSelectedMaterialId(val)}
              placeholder="选择附属资料"
              style={{ width: 220 }}
              disabled={!selectedCourseId}
              showSearch
              optionFilterProp="label"
              options={materials.map((m) => ({
                value: m.id,
                label: m.source_file,
              }))}
              notFoundContent={
                materials.length === 0 ? '该课程暂无附属资料' : '无匹配资料'
              }
            />
            {selectedMaterialId && (
              <Button
                type={hasExisting ? 'default' : 'primary'}
                icon={<ExperimentOutlined />}
                onClick={handleClassify}
                loading={classifying}
              >
                {hasExisting ? '重新分类' : 'LLM 分类'}
              </Button>
            )}
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                if (selectedMaterialId) loadChunkClassification(selectedMaterialId)
              }}
              disabled={!selectedMaterialId}
            >
              刷新
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          message="流程：附属资料 → 语义切片 → LLM 分类到章节 → 自动存入"
          description="选择课程和附属资料后，若已分类则直接展示结果。点击「LLM 分类」可触发 AI 自动归类，点击「重新分类」可覆盖已有结果。"
          style={{ marginBottom: 16 }}
        />

        {!selectedCourseId ? (
          <Empty description="请先选择课程" />
        ) : !selectedMaterialId ? (
          <Empty description="请选择一份附属资料查看其切片分类" />
        ) : loading ? (
          <div style={{ textAlign: 'center', padding: 48 }}>
            <Spin tip="加载分类结果..." />
          </div>
        ) : chunks.length > 0 ? (
          <>
            <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ color: '#666' }}>
                共 {chunks.length} 个切片
              </span>
              {hasExisting && (
                <Tag icon={<CheckCircleOutlined />} color="success">
                  已有分类结果
                </Tag>
              )}
            </div>
            <Table
              dataSource={chunks}
              columns={columns}
              rowKey="chunk_id"
              size="small"
              scroll={{ x: 960 }}
              pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total: number) => `共 ${total} 个切片` }}
            />
          </>
        ) : (
          <Empty
            description={
              <span>
                该资料尚未分类
                <br />
                <span style={{ fontSize: 12, color: '#999' }}>
                  请点击「LLM 分类」按钮开始 AI 自动归类
                </span>
              </span>
            }
          />
        )}
      </Card>
    </div>
  )
}