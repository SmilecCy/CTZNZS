// ============================================================
// 文件：pages/admin/ChapterManage.tsx
// 用途：章节管理页 —— 选择课程后显示大模型识别后的章节标题
// ============================================================

import { useEffect, useState } from 'react'
import {
  Card,
  Tree,
  Button,
  Modal,
  Input,
  message,
  Space,
  Popconfirm,
  Spin,
  Empty,
  Form,
  Select,
  Tag,
  Alert,
  List,
  Result,
} from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  FolderOutlined,
  ReloadOutlined,
  RobotOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import * as adminApi from '../../api/admin'
import type { ChapterTreeItem, Material } from '../../api/admin'
import type { Course } from '../../types'
import { extractErrorMessage } from '../../api/client'
import axios from 'axios'

// 内联 adminClient（用于 extract-chapters）
const adminClient = axios.create({ baseURL: '', timeout: 120000, headers: { 'Content-Type': 'application/json' } })
adminClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

interface TreeNode {
  key: string
  id: number
  name: string
  summary: string | null
  children?: TreeNode[]
}

export default function ChapterManage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null)
  const [treeData, setTreeData] = useState<TreeNode[]>([])
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingNode, setEditingNode] = useState<ChapterTreeItem | null>(null)
  const [parentId, setParentId] = useState<number | null>(null)
  const [form] = Form.useForm()

  // 该课程的绑定资料
  const [boundMaterials, setBoundMaterials] = useState<Material[]>([])
  const [extracting, setExtracting] = useState(false)

  useEffect(() => {
    adminApi.listAllCourses().then(setCourses)
  }, [])

  // ---------- 加载章节树 ----------
  const loadChapters = async (courseId: number) => {
    setLoading(true)
    setSelectedCourseId(courseId)
    setErrorMsg(null)
    setTreeData([])
    setBoundMaterials([])

    try {
      const [tree, mats] = await Promise.all([
        adminApi.listCourseChapters(courseId),
        adminApi.listMaterials({ courseId }),
      ])
      setTreeData(buildTreeNodes(tree))
      setBoundMaterials(mats)
    } catch (err: unknown) {
      const msg = extractErrorMessage(err)
      setErrorMsg(msg)
    } finally {
      setLoading(false)
    }
  }

  // ---------- ChapterTreeItem[] → TreeDataNode[] ----------
  const buildTreeNodes = (list: ChapterTreeItem[]): TreeNode[] =>
    list.map((ch) => ({
      key: String(ch.id),
      id: ch.id,
      name: ch.name,
      summary: ch.summary,
      children: buildTreeNodes(ch.children),
    }))

  // ---------- 触发章节抽取 ----------
  const handleExtract = async (materialId: number) => {
    setExtracting(true)
    try {
      const res = await adminClient.post(`/api/admin/materials/${materialId}/extract-chapters`, {
        create_knowledge_points: false,
      })
      const data = res.data as { chapter_count?: number; message?: string }
      message.success(data.message || `已抽取 ${data.chapter_count || 0} 个章节`)
      if (selectedCourseId) await loadChapters(selectedCourseId)
    } catch (err: unknown) {
      message.error(extractErrorMessage(err))
    } finally {
      setExtracting(false)
    }
  }

  // ---------- 新增 ----------
  const handleAdd = (parentId: number | null = null) => {
    setEditingNode(null)
    setParentId(parentId)
    form.resetFields()
    setModalVisible(true)
  }

  // ---------- 编辑 ----------
  const handleEdit = (node: TreeNode) => {
    const findChapter = (list: ChapterTreeItem[], id: number): ChapterTreeItem | null => {
      for (const ch of list) {
        if (ch.id === id) return ch
        const found = findChapter(ch.children, id)
        if (found) return found
      }
      return null
    }

    if (!selectedCourseId) return
    adminApi.listCourseChapters(selectedCourseId).then((tree) => {
      const ch = findChapter(tree, node.id)
      if (!ch) return
      setEditingNode(ch)
      setParentId(null)
      form.setFieldsValue({ name: ch.name, summary: ch.summary })
      setModalVisible(true)
    })
  }

  // ---------- 删除 ----------
  const handleDelete = async (chapterId: number) => {
    try {
      await adminApi.deleteChapter(chapterId)
      message.success('已删除')
      if (selectedCourseId) loadChapters(selectedCourseId)
    } catch (err) {
      message.error(extractErrorMessage(err))
    }
  }

  // ---------- 提交 ----------
  const handleSubmit = async () => {
    if (!selectedCourseId) return
    try {
      const values = await form.validateFields()
      if (editingNode) {
        await adminApi.updateChapter(editingNode.id, {
          name: values.name,
          summary: values.summary,
        })
        message.success('已更新')
      } else {
        await adminApi.createChapter({
          course_id: selectedCourseId,
          name: values.name,
          parent_id: parentId,
          summary: values.summary,
        })
        message.success('已创建')
      }
      setModalVisible(false)
      loadChapters(selectedCourseId)
    } catch {
      // validation failed
    }
  }

  // ---------- 渲染树节点标题 ----------
  const renderTitle = (node: TreeNode) => (
    <Space size={4}>
      <FolderOutlined style={{ color: '#1677ff' }} />
      <span>{node.name}</span>
      {node.summary && (
        <Tag color="geekblue" style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {node.summary}
        </Tag>
      )}
      <Button
        size="small" type="text"
        icon={<EditOutlined />}
        onClick={(e) => { e.stopPropagation(); handleEdit(node) }}
      />
      <Button
        size="small" type="text"
        icon={<PlusOutlined />}
        onClick={(e) => { e.stopPropagation(); handleAdd(node.id) }}
      />
      <Popconfirm
        title="确定删除此章节及子章节？"
        onConfirm={(e) => { e?.stopPropagation(); handleDelete(node.id) }}
        onCancel={(e) => e?.stopPropagation()}
      >
        <Button size="small" type="text" danger icon={<DeleteOutlined />}
          onClick={(e) => e.stopPropagation()} />
      </Popconfirm>
    </Space>
  )

  // ---------- 计算状态 ----------
  const hasChapters = treeData.length > 0
  const textbooks = boundMaterials.filter((m) => m.upload_type === 'textbook')
  const hasTextbook = textbooks.length > 0

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="章节管理"
        extra={
          <Space>
            <Select
              showSearch
              placeholder="请选择课程"
              style={{ width: 220 }}
              value={selectedCourseId}
              onChange={(id) => { if (id) loadChapters(id) }}
              optionFilterProp="label"
              options={courses.map((c) => ({
                label: c.display_name || c.name,
                value: c.id,
              }))}
            />
            {selectedCourseId && (
              <>
                <Button icon={<ReloadOutlined />} onClick={() => loadChapters(selectedCourseId)}>
                  刷新
                </Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => handleAdd(null)}>
                  添加章节
                </Button>
              </>
            )}
          </Space>
        }
      >
        {loading ? (
          <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
        ) : errorMsg ? (
          <Result status="error" title="加载失败" subTitle={errorMsg}
            extra={<Button onClick={() => selectedCourseId && loadChapters(selectedCourseId)}>重试</Button>} />
        ) : hasChapters ? (
          <Tree treeData={treeData} titleRender={renderTitle}
            defaultExpandAll blockNode showLine />
        ) : selectedCourseId ? (
          <Empty description="暂无章节">
            {hasTextbook ? (
              <div style={{ marginTop: 16 }}>
                <Alert
                  type="info" showIcon
                  message="该课程已绑定以下教材，点击「抽取」让大模型自动识别章节结构"
                  style={{ marginBottom: 12 }}
                />
                <List
                  size="small"
                  dataSource={textbooks}
                  renderItem={(m) => (
                    <List.Item
                      actions={[
                        <Button
                          key="extract"
                          type="primary" size="small"
                          icon={<RobotOutlined />}
                          loading={extracting}
                          onClick={() => handleExtract(m.id)}
                        >
                          抽取章节
                        </Button>,
                      ]}
                    >
                      <Space>
                        <FileTextOutlined />
                        {m.source_file}
                      </Space>
                    </List.Item>
                  )}
                />
              </div>
            ) : (
              <div style={{ marginTop: 16 }}>
                <Alert
                  type="warning" showIcon
                  message="该课程未绑定教材"
                  description="请先在「资料上传」中上传教材，或在「课程管理」中为课程绑定教材，系统会自动识别章节结构。"
                />
              </div>
            )}
          </Empty>
        ) : (
          <Empty description="请先选择课程" />
        )}
      </Card>

      <Modal
        title={editingNode ? '编辑章节' : '新增章节'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="章节标题"
            rules={[{ required: true, message: '请输入章节标题' }]}>
            <Input placeholder='如"第一章 商法概述"' />
          </Form.Item>
          <Form.Item name="summary" label="摘要">
            <Input.TextArea rows={3} placeholder="可选，1–2 句话概括本章内容" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}