// ============================================================
// 文件：pages/admin/MaterialUpload.tsx
// 用途：资料上传页 —— 教材 / 附属资料两个独立入口
// ============================================================

import { useEffect, useRef, useState } from 'react'
import {
  Card,
  Upload,
  Button,
  Table,
  Tag,
  Progress,
  Space,
  message,
} from 'antd'
import {
  BookOutlined,
  FileAddOutlined,
  InboxOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import * as adminApi from '../../api/admin'
import type { ParseTask } from '../../api/admin'
import { extractErrorMessage } from '../../api/client'

const { Dragger } = Upload

export default function MaterialUpload() {
  const [tasks, setTasks] = useState<ParseTask[]>([])
  const [uploadingTextbook, setUploadingTextbook] = useState(false)
  const [uploadingSupplement, setUploadingSupplement] = useState(false)
  const [loading, setLoading] = useState(false)

  const pollTimer = useRef<number | null>(null)

  const refresh = async () => {
    try {
      const data = await adminApi.listParseTasks()
      setTasks(data.tasks)
    } catch (err) {
      message.error(extractErrorMessage(err))
    }
  }

  useEffect(() => {
    setLoading(true)
    refresh().finally(() => setLoading(false))
    pollTimer.current = window.setInterval(refresh, 2000)
    return () => {
      if (pollTimer.current !== null) window.clearInterval(pollTimer.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleUploadTextbook = async (file: File) => {
    setUploadingTextbook(true)
    try {
      const task = await adminApi.uploadTextbook(file)
      message.success(`教材「${file.name}」已上传（任务 id=${task.id}）`)
      await refresh()
    } catch (err) {
      message.error(extractErrorMessage(err))
    } finally {
      setUploadingTextbook(false)
    }
    return false
  }

  const handleUploadSupplement = async (file: File) => {
    setUploadingSupplement(true)
    try {
      const task = await adminApi.uploadSupplement(file)
      message.success(`附属资料「${file.name}」已上传（任务 id=${task.id}）`)
      await refresh()
    } catch (err) {
      message.error(extractErrorMessage(err))
    } finally {
      setUploadingSupplement(false)
    }
    return false
  }

  const handleRetry = async (taskId: number) => {
    try {
      await adminApi.retryParseTask(taskId)
      message.success('已提交重试')
      await refresh()
    } catch (err) {
      message.error(extractErrorMessage(err))
    }
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '文件名', dataIndex: 'source_file', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (status: string) => {
        const colorMap: Record<string, string> = {
          pending: 'default',
          running: 'processing',
          done: 'success',
          failed: 'error',
        }
        const labelMap: Record<string, string> = {
          pending: '排队中',
          running: '解析中',
          done: '完成',
          failed: '失败',
        }
        return <Tag color={colorMap[status]}>{labelMap[status] || status}</Tag>
      },
    },
    {
      title: '进度',
      dataIndex: 'progress',
      width: 200,
      render: (progress: number, row: ParseTask) => {
        if (row.status === 'done') return <Progress percent={100} size="small" status="success" />
        if (row.status === 'failed') return <Progress percent={progress} size="small" status="exception" />
        return (
          <Progress
            percent={progress}
            size="small"
            status="active"
            format={(p) => `${p}% ${row.stage || ''}`}
          />
        )
      },
    },
    {
      title: '结果',
      key: 'result',
      width: 200,
      render: (_: unknown, row: ParseTask) => {
        if (row.status === 'done') {
          return (
            <Space size={4} wrap>
              <Tag>页数 {row.page_count}</Tag>
              <Tag>块数 {row.chunk_count}</Tag>
              {row.ocr_used && <Tag color="orange">OCR</Tag>}
            </Space>
          )
        }
        if (row.status === 'failed' && row.error) {
          return (
            <span style={{ color: '#ff4d4f', fontSize: 12 }} title={row.error}>
              {row.error.slice(0, 40)}...
            </span>
          )
        }
        return null
      },
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 160,
      render: (v: string) => (v ? v.slice(0, 19) : ''),
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: unknown, row: ParseTask) => (
        <Space>
          {row.status === 'failed' && (
            <Button size="small" icon={<ReloadOutlined />} onClick={() => handleRetry(row.id)}>
              重试
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      {/* 教材上传 */}
      <Card
        title={
          <Space>
            <BookOutlined />
            <span>教材上传</span>
            <Tag color="blue">每门课程限一本</Tag>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Dragger
          name="file"
          multiple={true}
          beforeUpload={(file) => {
            handleUploadTextbook(file)
            return false
          }}
          showUploadList={false}
          disabled={uploadingTextbook}
        >
          <p className="ant-upload-drag-icon">
            <BookOutlined style={{ fontSize: 48, color: '#1677ff' }} />
          </p>
          <p className="ant-upload-text">
            {uploadingTextbook ? '上传中…' : '点击或拖拽教材文件上传'}
          </p>
          <p className="ant-upload-hint">
            上传课程的教材（PDF/DOCX），解析后可抽取章节结构。每门课最多一本教材。
          </p>
        </Dragger>
      </Card>

      {/* 附属资料上传 */}
      <Card
        title={
          <Space>
            <FileAddOutlined />
            <span>附属资料上传</span>
            <Tag color="green">无数量限制</Tag>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Dragger
          name="file"
          multiple={true}
          beforeUpload={(file) => {
            handleUploadSupplement(file)
            return false
          }}
          showUploadList={false}
          disabled={uploadingSupplement}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">
            {uploadingSupplement ? '上传中…' : '点击或拖拽附属资料上传'}
          </p>
          <p className="ant-upload-hint">
            上传讲义、参考书目、法条原文、习题集等。支持批量上传，单文件不超过 50MB。
          </p>
        </Dragger>
      </Card>

      {/* 解析任务列表 */}
      <Card
        title="解析任务"
        extra={
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
        }
      >
        <Table
          rowKey="id"
          dataSource={tasks}
          columns={columns}
          loading={loading}
          pagination={{ pageSize: 20 }}
          locale={{ emptyText: '还没有上传记录，上传资料后会在这里看到解析进度。' }}
        />
      </Card>
    </div>
  )
}