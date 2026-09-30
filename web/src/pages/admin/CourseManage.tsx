// ============================================================
// 文件：pages/admin/CourseManage.tsx
// 用途：课程管理（增删改、启用停用、彻底删除、合并）
// ============================================================

import { useEffect, useState } from 'react'
import {
  Card,
  Table,
  Button,
  Space,
  Modal,
  Form,
  Input,
  Select,
  message,
  Popconfirm,
  Tag,
  Alert,
  Divider,
} from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  StopOutlined,
  ExclamationCircleOutlined,
  LinkOutlined,
} from '@ant-design/icons'
import * as adminApi from '../../api/admin'
import type { CourseDeletePreview, Material } from '../../api/admin'
import { extractErrorMessage } from '../../api/client'
import type { Course } from '../../types'

export default function CourseManage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)

  // 彻底删除相关
  const [hardDeleteOpen, setHardDeleteOpen] = useState(false)
  const [hardDeleteTarget, setHardDeleteTarget] = useState<Course | null>(null)
  const [hardDeletePreview, setHardDeletePreview] = useState<CourseDeletePreview | null>(null)
  const [hardDeleting, setHardDeleting] = useState(false)

  // 绑定教材相关
  const [bindModalOpen, setBindModalOpen] = useState(false)
  const [bindTargetCourse, setBindTargetCourse] = useState<Course | null>(null)
  const [bindMaterials, setBindMaterials] = useState<Material[]>([])
  const [bindLoading, setBindLoading] = useState(false)
  const [bindSubmitting, setBindSubmitting] = useState(false)

  // 所有资料（用于展示每个课程绑定的教材）
  const [allMaterials, setAllMaterials] = useState<Material[]>([])

  const [createForm] = Form.useForm()
  const [bindForm] = Form.useForm()

  // ---------- 加载课程 ----------
  const refresh = async () => {
    setLoading(true)
    try {
      const [list, mats] = await Promise.all([
        adminApi.listAllCourses(),
        adminApi.listMaterials({}),
      ])
      setCourses(list)
      setAllMaterials(mats)
    } catch (err) {
      message.error(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  // ---------- 建课程 ----------
  const handleCreate = async (values: {
    name: string
    display_name?: string
    description?: string
    question_focus?: string
  }) => {
    try {
      await adminApi.createCourse({
        name: values.name,
        display_name: values.display_name || values.name,
        description: values.description || '',
        question_focus: values.question_focus || '',
      })
      message.success('建课程成功')
      setCreateModalOpen(false)
      createForm.resetFields()
      await refresh()
    } catch (err) {
      message.error(extractErrorMessage(err))
    }
  }

  // ---------- 停用 ----------
  const handleSoftDelete = async (courseId: number) => {
    try {
      await adminApi.deleteCourse(courseId)
      message.success('已停用')
      await refresh()
    } catch (err) {
      message.error(extractErrorMessage(err))
    }
  }

  // ---------- 启用 ----------
  const handleRestore = async (courseId: number) => {
    try {
      await adminApi.restoreCourse(courseId)
      message.success('已启用')
      await refresh()
    } catch (err) {
      message.error(extractErrorMessage(err))
    }
  }

  // ---------- 打开彻底删除弹窗 ----------
  const openHardDelete = async (c: Course) => {
    setHardDeleteTarget(c)
    setHardDeletePreview(null)
    setHardDeleteOpen(true)

    try {
      const preview = await adminApi.getCourseDeletePreview(c.id)
      setHardDeletePreview(preview)
    } catch (err) {
      message.error(extractErrorMessage(err))
      setHardDeleteOpen(false)
    }
  }

  // ---------- 执行彻底删除 ----------
  const handleHardDelete = async () => {
    if (!hardDeleteTarget) return

    setHardDeleting(true)
    try {
      const result = await adminApi.hardDeleteCourse(hardDeleteTarget.id)
      message.success(result.message || '已彻底删除')
      setHardDeleteOpen(false)
      setHardDeleteTarget(null)
      await refresh()
    } catch (err) {
      message.error(extractErrorMessage(err))
    } finally {
      setHardDeleting(false)
    }
  }

  // ---------- 打开绑定教材弹窗 ----------
  const openBindMaterial = async (course: Course) => {
    setBindTargetCourse(course)
    setBindLoading(true)
    setBindModalOpen(true)
    bindForm.resetFields()

    try {
      const textbooks = await adminApi.listMaterials({ uploadType: 'textbook' })
      setBindMaterials(textbooks)
    } catch (err) {
      message.error(extractErrorMessage(err))
      setBindModalOpen(false)
    } finally {
      setBindLoading(false)
    }
  }

  // ---------- 执行绑定 ----------
  const handleBind = async (values: { material_id: number }) => {
    if (!bindTargetCourse) return

    setBindSubmitting(true)
    try {
      const result = await adminApi.confirmMaterial(values.material_id, {
        course_id: bindTargetCourse.id,
        create_knowledge_points: false,
      })
      message.success(result.message || '绑定成功')
      setBindModalOpen(false)
      setBindTargetCourse(null)
    } catch (err) {
      message.error(extractErrorMessage(err))
    } finally {
      setBindSubmitting(false)
    }
  }

  // ---------- 表格列 ----------
  const columns = [
    {
      title: '#',
      dataIndex: 'id',
      width: 60,
      render: (_: unknown, __: Course, index: number) => index + 1,
    },
    {
      title: '课程名（唯一标识）',
      dataIndex: 'name',
      width: 180,
    },
    {
      title: '展示名',
      dataIndex: 'display_name',
      width: 180,
    },
    {
      title: '绑定的教材',
      dataIndex: 'id' as keyof Course,
      ellipsis: true,
      render: (_: unknown, row: Course) => {
        const bound = allMaterials.filter(
          (m) => m.course_id === row.id && m.upload_type === 'textbook',
        )
        if (bound.length === 0) return '—'
        return (
          <Space size={4} wrap>
            {bound.map((m) => (
              <Tag key={m.id} color="blue">{m.source_file}</Tag>
            ))}
          </Space>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 100,
      render: (_: unknown, row: Course) => {
        // 有些后端可能不返回 is_active 字段
        const isActive = row.is_active !== 0
        return isActive ? (
          <Tag color="green">启用</Tag>
        ) : (
           <Tag color="default">已停用</Tag>
        )
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 340,
      render: (_: unknown, row: Course) => {
        const isActive = row.is_active !== 0

        return (
          <Space>
            {isActive ? (
              <Popconfirm
                title="确定停用这门课程吗？"
                description="停用后学生端不再显示，但数据保留，可以重新启用。"
                onConfirm={() => handleSoftDelete(row.id)}
                okText="停用"
                cancelText="取消"
              >
                <Button size="small" icon={<StopOutlined />}>
                  停用
                </Button>
              </Popconfirm>
            ) : (
              <Button
                size="small"
                type="primary"
                icon={<CheckCircleOutlined />}
                onClick={() => handleRestore(row.id)}
              >
                启用
              </Button>
            )}
            <Button
              size="small"
              icon={<LinkOutlined />}
              onClick={() => openBindMaterial(row)}
            >
              绑定教材
            </Button>
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => openHardDelete(row)}
            >
              彻底删除
            </Button>
          </Space>
        )
      },
    },
  ]

  // ---------- 渲染 ----------
  return (
    <div>
      <Card
        title="课程管理"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalOpen(true)}
          >
            新建课程
          </Button>
        }
      >
        <Alert
          type="info"
          showIcon
          message="三种操作的区别"
          description={
            <div>
              <div><b>停用</b>：软删除，学生端不显示，但数据保留，可随时启用。</div>
              <div><b>启用</b>：把停用的课程重新启用。</div>
              <div><b>彻底删除</b>：物理删除，会连带删掉所有题目、错题、试卷。不可恢复。</div>
            </div>
          }
          style={{ marginBottom: 16 }}
        />

        {courses.length === 0 && !loading ? (
          <Alert
            type="info"
            showIcon
            message="还没有课程"
            description="点击右上角「新建课程」开始。"
          />
        ) : (
          <Table
            rowKey="id"
            dataSource={courses}
            columns={columns}
            loading={loading}
            pagination={{ pageSize: 20 }}
          />
        )}
      </Card>

      {/* ========== 新建课程弹窗 ========== */}
      <Modal
        title="新建课程"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onOk={() => createForm.submit()}
        okText="创建"
        cancelText="取消"
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="name"
            label="课程名（唯一标识）"
            rules={[{ required: true, message: '请输入课程名' }]}
            extra="例如：商法、习概。用于系统内部，学生看不到。"
          >
            <Input placeholder="例如：商法" />
          </Form.Item>

          <Form.Item
            name="display_name"
            label="展示名"
            extra="学生端显示的名字。不填就用课程名。"
          >
            <Input placeholder="例如：商法（侵权责任法）" />
          </Form.Item>

          <Form.Item name="description" label="课程描述">
            <Input.TextArea rows={2} placeholder="可选" />
          </Form.Item>

          <Form.Item name="question_focus" label="出题侧重">
            <Input placeholder="例如：构成要件辨析、案例适用" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ========== 彻底删除弹窗 ========== */}
      <Modal
        title={
          <Space>
            <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
            彻底删除课程
          </Space>
        }
        open={hardDeleteOpen}
        onCancel={() => setHardDeleteOpen(false)}
        onOk={handleHardDelete}
        okText="确认彻底删除"
        okButtonProps={{ danger: true, loading: hardDeleting }}
        cancelText="取消"
        width={640}
      >
        {hardDeleteTarget && (
          <>
            <Alert
              type="error"
              showIcon
              message="此操作不可恢复"
              description="课程及其关联的所有数据都会被物理删除，无法找回。"
              style={{ marginBottom: 16 }}
            />

            <p>
              <strong>课程：</strong>
              {hardDeleteTarget.display_name || hardDeleteTarget.name}
              （id={hardDeleteTarget.id}）
            </p>

            <Divider />

            {hardDeletePreview ? (
              <>
                <p>
                  <strong>将被删除：</strong>
                </p>
                <ul>
                  <li>课程本身</li>
                  <li>知识点：{hardDeletePreview.knowledge_point_count} 个</li>
                  <li>
                    <b style={{ color: '#ff4d4f' }}>
                      题目：{hardDeletePreview.question_count} 道
                    </b>
                  </li>
                  <li>
                    <b style={{ color: '#ff4d4f' }}>
                      学生错题：{hardDeletePreview.wrong_question_count} 条
                    </b>
                  </li>
                  <li>试卷：{hardDeletePreview.paper_count} 张</li>
                </ul>

                <p style={{ marginTop: 16 }}>
                  <strong>不会被删除：</strong>
                </p>
                <ul>
                  <li>
                    归属这门课的 {hardDeletePreview.material_count} 份资料
                    <span style={{ color: '#888' }}>
                      （资料会保留，但失去课程归属）
                    </span>
                  </li>
                  <li>LLM 调用审计日志（成本审计需要留痕）</li>
                </ul>

                {hardDeletePreview.question_count > 0 && (
                  <Alert
                    type="warning"
                    showIcon
                    message={`注意：这门课有 ${hardDeletePreview.question_count} 道题`}
                    description="如果只是不想让它出现在列表里，建议用「停用」而不是「彻底删除」。"
                    style={{ marginTop: 16 }}
                  />
                )}
              </>
            ) : (
              <div style={{ textAlign: 'center', padding: 20 }}>加载中…</div>
            )}

            <Divider />

            <p style={{ color: '#666' }}>
              确定要彻底删除吗？此操作无法撤销。
            </p>
          </>
        )}
      </Modal>

      {/* ========== 绑定教材弹窗 ========== */}
      <Modal
        title={`绑定教材 — ${bindTargetCourse?.display_name || bindTargetCourse?.name || ''}`}
        open={bindModalOpen}
        onCancel={() => setBindModalOpen(false)}
        onOk={() => bindForm.submit()}
        okText="确认绑定"
        cancelText="取消"
        confirmLoading={bindSubmitting}
        width={560}
      >
        {bindLoading ? (
          <div style={{ textAlign: 'center', padding: 20 }}>加载中…</div>
        ) : (
          <>
            <Alert
              type="info"
              showIcon
              message={`把已上传的资料关联到「${bindTargetCourse?.display_name || bindTargetCourse?.name || ''}」课程下，出题时会从这里取上下文。`}
              style={{ marginBottom: 16 }}
            />

            <Form form={bindForm} layout="vertical" onFinish={handleBind}>
              <Form.Item
                name="material_id"
                label="选择资料"
                rules={[{ required: true, message: '请选择一份资料' }]}
              >
                <Select
                  showSearch
                  placeholder="搜索并选择资料"
                  optionFilterProp="label"
                  loading={bindLoading}
                  options={bindMaterials.map((m) => ({
                    label: `${m.source_file}${m.course_id ? `  [当前归属: #${m.course_id}]` : '  [未归属]'}`,
                    value: m.id,
                  }))}
                />
              </Form.Item>
            </Form>
          </>
        )}
      </Modal>
    </div>
  )
}