import { useState, useEffect } from 'react'
import { Table, Input, Button, Space, Popconfirm, message, Tag, Modal, Form, InputNumber, Alert } from 'antd'
import { SearchOutlined, PlusOutlined, EyeOutlined, DeleteOutlined, SettingOutlined, ReloadOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { groupApi } from '../utils/api'

function GroupList() {
  const navigate = useNavigate()
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [selectedRowKeys, setSelectedRowKeys] = useState([])
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchResult, setBatchResult] = useState(null)
  const [createModalVisible, setCreateModalVisible] = useState(false)
  const [batchQpsModalVisible, setBatchQpsModalVisible] = useState(false)
  const [createForm] = Form.useForm()
  const [batchQpsForm] = Form.useForm()

  // 加载分组列表（支持 silent 静默轮询刷新）
  const loadGroups = async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const result = await groupApi.list()
      const list = result.data || []
      setGroups(list)
      return list
    } catch (error) {
      if (!silent) {
        message.error('加载分组列表失败：' + (error.message || '未知错误'))
      }
      return null
    } finally {
      if (!silent) setLoading(false)
    }
  }

  useEffect(() => {
    loadGroups()
    const timer = setInterval(() => {
      loadGroups(true)
    }, 5000)
    return () => clearInterval(timer)
  }, [])

  const columns = [
    {
      title: '分组',
      dataIndex: 'groupName',
      key: 'groupName'
    },
    {
      title: '所属用户',
      dataIndex: 'userName',
      key: 'userName'
    },
    {
      title: 'QPS 限制',
      dataIndex: 'quotaQpsGroup',
      key: 'quotaQpsGroup'
    },
    {
      title: '设备 qps 限制',
      dataIndex: 'quotaQpsPerDevice',
      key: 'quotaQpsPerDevice'
    },
    {
      title: '创建时间',
      dataIndex: 'createTime',
      key: 'createTime'
    },
    {
      title: '可用客户端',
      dataIndex: 'availableClients',
      key: 'availableClients',
      render: (count) => <Tag color="green">{count}</Tag>
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/group/${record.groupName}`)}
          >
            详情
          </Button>
          <Popconfirm
            title="确定删除该分组吗？"
            onConfirm={() => handleDelete(record)}
            okText="确定"
            cancelText="取消"
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ]

  const filteredGroups = groups.filter((group) =>
    group.groupName.toLowerCase().includes(searchText.toLowerCase()) ||
    group.userName.toLowerCase().includes(searchText.toLowerCase())
  )

  const handleDelete = async (record) => {
    try {
      await groupApi.delete({ groupName: record.groupName })
      message.success('分组删除成功')
      loadGroups()
    } catch (error) {
      message.error('删除分组失败：' + (error.message || '未知错误'))
    }
  }

  const selectedNames = groups
    .filter((group) => selectedRowKeys.includes(group.id))
    .map((group) => group.groupName)

  // 批量操作后刷新列表并清除已成功项的选择，失败项保留选中便于重试。
  // 仅保留刷新后仍存在的分组，避免已不存在（如 not found）的分组留下幽灵选中态。
  const applyBatchResult = async (result) => {
    const { succeeded = [], failed = [] } = result || {}
    const failedNames = failed.map((item) => item.groupName)
    const freshGroups = (await loadGroups()) || []
    const failedKeys = freshGroups
      .filter((group) => failedNames.includes(group.groupName))
      .map((group) => group.id)
    setSelectedRowKeys(failedKeys)
    setBatchResult(failed)
    return succeeded.length
  }

  const handleBatchDelete = async () => {
    setBatchLoading(true)
    try {
      const result = await groupApi.batchDelete(selectedNames)
      const succeededCount = await applyBatchResult(result.data)
      if (succeededCount > 0) message.success(`成功删除 ${succeededCount} 个分组`)
    } catch (error) {
      message.error('批量删除失败：' + (error.message || '未知错误'))
    } finally {
      setBatchLoading(false)
    }
  }

  const toggleBatchQpsModal = (open) => {
    setBatchQpsModalVisible(open)
    if (!open) batchQpsForm.resetFields()
  }

  const handleBatchQpsOk = async () => {
    let values
    try {
      values = await batchQpsForm.validateFields()
    } catch {
      return // 表单校验失败，antd 已在字段上展示错误
    }

    const payload = { groupNames: selectedNames }
    if (values.quotaQpsGroup > 0) payload.quotaQpsGroup = values.quotaQpsGroup
    if (values.quotaQpsPerDevice > 0) payload.quotaQpsPerDevice = values.quotaQpsPerDevice
    if (payload.quotaQpsGroup === undefined && payload.quotaQpsPerDevice === undefined) {
      message.warning('请至少填写一项 QPS 限制')
      return
    }

    setBatchLoading(true)
    try {
      const result = await groupApi.batchUpdateQps(payload)
      const succeededCount = await applyBatchResult(result.data)
      if (succeededCount > 0) message.success(`成功更新 ${succeededCount} 个分组的 QPS 限制`)
      toggleBatchQpsModal(false)
    } catch (error) {
      message.error('批量修改 QPS 失败：' + (error.message || '未知错误'))
    } finally {
      setBatchLoading(false)
    }
  }

  const toggleCreateModal = (open) => {
    setCreateModalVisible(open)
    if (!open) createForm.resetFields()
  }

  const handleCreateModalOk = async () => {
    try {
      const values = await createForm.validateFields()
      await groupApi.create({
        groupName: values.groupName,
        quotaQpsGroup: values.quotaQpsGroup || 100,
        quotaQpsPerDevice: values.quotaQpsPerDevice || -1
      })
      message.success('分组创建成功')
      toggleCreateModal(false)
      loadGroups()
    } catch (error) {
      if (error.response?.status === 409) {
        message.error('分组名称已存在')
      } else if (error.errors) {
        // 表单验证错误
        return
      } else {
        message.error('创建分组失败：' + (error.message || '未知错误'))
      }
    }
  }

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">分组列表</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => toggleCreateModal(true)}>
          创建分组
        </Button>
      </div>

      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
        <Input
          placeholder="请输入关键词进行查询"
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => {
            setSearchText(e.target.value)
            setCurrentPage(1)
            setSelectedRowKeys([])
          }}
          style={{ width: 300 }}
        />
        <Button icon={<ReloadOutlined />} onClick={() => loadGroups(false)} loading={loading}>
          刷新
        </Button>
        {selectedRowKeys.length > 0 && (
          <Space>
            <span>已选 {selectedRowKeys.length} 项</span>
            <Popconfirm
              title={`确定删除选中的 ${selectedNames.length} 个分组吗？`}
              description="分组下的设备与 Action 会一并删除"
              onConfirm={handleBatchDelete}
              okText="确定"
              cancelText="取消"
            >
              <Button danger icon={<DeleteOutlined />} loading={batchLoading}>
                批量删除
              </Button>
            </Popconfirm>
            <Button
              icon={<SettingOutlined />}
              onClick={() => toggleBatchQpsModal(true)}
              loading={batchLoading}
            >
              批量修改 QPS
            </Button>
            <Button type="link" onClick={() => setSelectedRowKeys([])}>
              取消选择
            </Button>
          </Space>
        )}
      </div>

      <Table
        columns={columns}
        dataSource={filteredGroups}
        rowKey="id"
        loading={loading}
        rowSelection={{
          selectedRowKeys,
          onChange: setSelectedRowKeys
        }}
        pagination={{
          current: currentPage,
          pageSize: 10,
          total: filteredGroups.length,
          showSizeChanger: false,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (page) => setCurrentPage(page)
        }}
      />

      <Modal
        title="创建分组"
        open={createModalVisible}
        onOk={handleCreateModalOk}
        onCancel={() => toggleCreateModal(false)}
        okText="确定"
        cancelText="取消"
      >
        <Form form={createForm} layout="vertical" initialValues={{ quotaQpsGroup: 100, quotaQpsPerDevice: -1 }}>
          <Form.Item
            name="groupName"
            label="分组名称"
            rules={[{ required: true, message: '请输入分组名称' }]}
          >
            <Input placeholder="请输入分组名称" />
          </Form.Item>
          <Form.Item
            name="quotaQpsGroup"
            label="分组 QPS 限制"
            rules={[{ required: true, message: '请输入 QPS 限制' }]}
          >
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="quotaQpsPerDevice"
            label="设备 QPS 限制"
            tooltip="设置为 -1 表示不限制"
          >
            <InputNumber min={-1} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`批量修改 QPS 限制（${selectedNames.length} 个分组）`}
        open={batchQpsModalVisible}
        onOk={handleBatchQpsOk}
        confirmLoading={batchLoading}
        onCancel={() => toggleBatchQpsModal(false)}
        okText="确定"
        cancelText="取消"
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="留空表示不修改该项，至少填写一项"
        />
        <Form form={batchQpsForm} layout="vertical">
          <Form.Item name="quotaQpsGroup" label="分组 QPS 限制">
            <InputNumber min={1} style={{ width: '100%' }} placeholder="留空则不修改" />
          </Form.Item>
          <Form.Item name="quotaQpsPerDevice" label="设备 QPS 限制">
            <InputNumber min={1} style={{ width: '100%' }} placeholder="留空则不修改" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="部分操作未生效"
        open={batchResult !== null && batchResult.length > 0}
        onOk={() => setBatchResult(null)}
        onCancel={() => setBatchResult(null)}
        okText="知道了"
        cancelText="关闭"
        footer={(_, { OkBtn, CancelBtn }) => (
          <Space>
            <CancelBtn />
            <OkBtn />
          </Space>
        )}
      >
        <ul style={{ paddingLeft: 20, margin: 0 }}>
          {(batchResult || []).map((item) => (
            <li key={item.groupName}>
              <strong>{item.groupName}</strong>：{item.reason}
            </li>
          ))}
        </ul>
      </Modal>
    </div>
  )
}

export default GroupList
