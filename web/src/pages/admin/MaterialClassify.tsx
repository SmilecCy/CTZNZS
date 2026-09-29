// ============================================================
// 文件：pages/admin/MaterialClassify.tsx
// 用途：资料分类页 —— 选目标课程，把未分类的附属资料关联到该课程
// ============================================================

import { useEffect, useState, useMemo } from 'react'
import {
  Card,
  Table,
  Button,
  Space,
  Tag,
  Select,
  message,
  Modal,
  Input,
  Divider,
  Alert,
  Popconfirm,
} from 'antd'
import {
  ReloadOutlined,
  DeleteOutlined,
  ExclamationCircleOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons'
import * as adminApi from '../../api/admin'
import type { Material, DeletePreview } from '../../api/admin'
import { extractErrorMessage } from '../../api/client'
import type { Course } from '../../types'

/** 类型 → 标签颜色 */
const TYPE_MAP: Record<string, { color: string; label: string }> = {
  textbook:   { color: 'blue',   label: '教材' },
  supplement: { color: 'green',  label: '附属资料' },
}

export default function MaterialClassify() {
  const [materials, setMaterials] = useState<Material[]>([])
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(false)
  const [targetCourseId, setTargetCourseId] = useState<number | undefined>(undefined)

  // 删除
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [deletePreview, setDeletePreview] = useState<DeletePreview | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Material | null>(null)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')
  const [deleting, setDeleting] = useState(false)

  // ---------- 加载 ----------
  const refresh = async () => {
    setLoading(true)
    try {
      const [all, courseList] = await Promise.all([
        adminApi.listMaterials({ uploadType: 'supplement' }),
        adminApi.listAllCourses(),
      ])
      // 教材置顶，同类型按上传时间倒序
      const sorted = all.sort((a, b) => {
        const aType = a.upload_type === 'textbook' ? 0 : 1
        const bType = b.upload_type === 'textbook' ? 0 : 1
        if (aType !== bType) return aType - bType
        return (b.uploaded_at || '').localeCompare(a.uploaded_at || '')
      })
      setMaterials(sorted)
      setCourses(courseList)
    } catch (err) {
      message.error(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  // ---------- 只显示未分类的附属资料（无课程归属） ----------
  const unclassifiedMaterials = useMemo(
    () => materials.filter((m) => !m.course_id),
    [materials],
  )

  // ---------- 分类到选中的课程 ----------
  const handleClassify = async (materialId: number) => {
    if (!targetCourseId) {
      message.warning('请先选择目标课程')
      return
    }
    setLoading(true)
    try {
      const result = await adminApi.confirmMaterial(materialId, {
        course_id: targetCourseId,
        create_knowledge_points: false,
      })
      message.success(result.message || '分类成功')
      await refresh()
    } catch (err) {
      message.error(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  // ---------- 打开删除弹窗 ----------
  const openDelete = async (material: Material) => {
    setDeleteTarget(material)
    setDeleteConfirmText('')
    setDeletePreview(null)
    setDeleteModalOpen(true)

    try {
      const preview = await adminApi.getDeletePreview(material.id)
      setDeletePreview(preview)
    } catch (err) {
      message.error(extractErrorMessage(err))
      setDeleteModalOpen(false)
    }
  }

  // ---------- 执行删除 ----------
  const handleDelete = async () => {
    if (!deleteTarget || !deletePreview) return

    if (deleteConfirmText !== deleteTarget.source_file) {
      message.error('资料名不匹配，请输入完整文件名')
      return
    }

    setDeleting(true)
    try {
      const result = await adminApi.deleteMaterial(deleteTarget.id)
      message.success(result.message || '已删除')
      setDeleteModalOpen(false)
      setDeleteTarget(null)
      await refresh()
    } catch (err) {
      message.error(extractErrorMessage(err))
    } finally {
      setDeleting(false)
    }
  }

  // ---------- 表格列 ----------
  const columns = [
    {
      title: '#',
      dataIndex: 'id',
      width: 60,
      render: (_: unknown, __: Material, index: number) => index + 1,
    },
    {
      title: '文件名',
      dataIndex: 'source_file',
      ellipsis: true,
      render: (v: string) => <span title={v}>{v}</span>,
    },
    {
      title: '类型',
      dataIndex: 'upload_type',
      width: 100,
      render: (v: string) => {
        const info = TYPE_MAP[v as keyof typeof TYPE_MAP] || TYPE_MAP.supplement
        return <Tag color={info.color}>{info.label}</Tag>
      },
    },
    {
      title: '上传时间',
      dataIndex: 'uploaded_at',
      width: 180,
      render: (v: string) => v || '—',
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: unknown, row: Material) => (
        <Space>
          <Popconfirm
            title="分类到该课程"
            description={`将「${row.source_file}」归入所选课程？`}
            onConfirm={() => handleClassify(row.id)}
            okText="分类"
            cancelText="取消"
            disabled={!targetCourseId}
          >
            <Button
              size="small"
              type="primary"
              icon={<FolderOpenOutlined />}
              disabled={!targetCourseId}
            >
              分类
            </Button>
          </Popconfirm>
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => openDelete(row)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  // ---------- 渲染 ----------
  return (
    <div>
      <Card
        title="资料分类"
        extra={
          <Space>
            <Select
              style={{ width: 200 }}
              placeholder="选择目标课程"
              value={targetCourseId}
              onChange={(val) => setTargetCourseId(val)}
              allowClear
              options={courses.map((c) => ({
                label: c.display_name || c.name,
                value: c.id,
              }))}
            />
            <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
              刷新
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          message="分类说明"
          description="只显示上传的附属资料（未归入任何课程）。选择目标课程后，点击「分类」按钮将资料归入该课程。教材请到「课程管理」页通过「绑定教材」处理。"
          style={{ marginBottom: 16 }}
        />

        {unclassifiedMaterials.length === 0 && !loading ? (
          <Alert
            type="success"
            showIcon
            message="没有待分类的附属资料"
            description="所有附属资料都已归入课程。"
          />
        ) : (
          <Table
            rowKey="id"
            dataSource={unclassifiedMaterials}
            columns={columns}
            loading={loading}
            pagination={{ pageSize: 20 }}
          />
        )}
      </Card>

      {/* ========== 删除确认弹窗 ========== */}
      <Modal
        title={
          <Space>
            <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
            确认删除资料
          </Space>
        }
        open={deleteModalOpen}
        onCancel={() => setDeleteModalOpen(false)}
        onOk={handleDelete}
        okText="确认删除"
        okButtonProps={{
          danger: true,
          disabled:
            !deletePreview ||
            !deletePreview.can_delete ||
            deleteConfirmText !== (deleteTarget?.source_file || ''),
          loading: deleting,
        }}
        cancelText="取消"
        width={640}
      >
        {deleteTarget && deletePreview && (
          <>
            <Alert
              type="error"
              showIcon
              message="此操作不可恢复"
              description="资料的原文件、向量索引、数据库记录都会被彻底删除。"
              style={{ marginBottom: 16 }}
            />

            {!deletePreview.can_delete && (
              <Alert
                type="warning"
                showIcon
                message={deletePreview.block_reason || '暂时无法删除'}
                style={{ marginBottom: 16 }}
              />
            )}

            <Divider />

            <p>
              <strong>将要删除：</strong>
            </p>
            <ul>
              <li>
                原文件 <code>{deleteTarget.source_file}</code>（从 data/uploads 删除）
              </li>
              <li>{deletePreview.chunk_count} 个向量块（从向量库删除）</li>
              <li>数据库中的资料记录和任务记录</li>
            </ul>

            <p style={{ marginTop: 16 }}>
              <strong>不会被删除：</strong>
            </p>
            <ul>
              <li>
                {deletePreview.question_count} 道来自这份资料的题目
                <span style={{ color: '#888' }}>
                  （它们已独立存在于题库，可到"题库浏览"手动废弃）
                </span>
              </li>
              <li>学生的错题和作答历史</li>
            </ul>

            <Divider />

            <p>
              <strong>请输入完整文件名确认删除：</strong>
            </p>
            <p style={{ color: '#888', fontSize: 12 }}>
              复制下面这行文件名，粘贴到输入框：
            </p>
            <p
              style={{
                padding: 8,
                background: '#f5f5f5',
                borderRadius: 4,
                fontFamily: 'monospace',
                wordBreak: 'break-all',
              }}
            >
              {deleteTarget.source_file}
            </p>
            <Input
              placeholder="粘贴完整文件名"
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
              style={{ marginTop: 8 }}
            />
          </>
        )}
      </Modal>
    </div>
  )
}