import { useEffect, useState } from 'react'
import { Button, Form, Input, InputNumber, Modal, Popconfirm, Space, Switch, Table, Tag, message } from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { userApi } from '../utils/api'

function UserList() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [quotaOpen, setQuotaOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState(null)
  const [createForm] = Form.useForm()
  const [quotaForm] = Form.useForm()

  const loadUsers = async () => {
    setLoading(true)
    try {
      const result = await userApi.list()
      setUsers(result.data || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadUsers()
  }, [])

  const filteredUsers = users.filter((user) => {
    const normalized = keyword.trim().toLowerCase()
    if (!normalized) {
      return true
    }
    return user.userName.toLowerCase().includes(normalized)
  })

  const handleCreate = async () => {
    const values = await createForm.validateFields()
    await userApi.add(values)
    message.success('用户已创建')
    setCreateOpen(false)
    createForm.resetFields()
    loadUsers()
  }

  const openQuotaModal = (user) => {
    setSelectedUser(user)
    quotaForm.setFieldsValue({ quotaQps: user.quotaQps })
    setQuotaOpen(true)
  }

  const handleUpdateQuota = async () => {
    const values = await quotaForm.validateFields()
    await userApi.updateQps({
      userId: selectedUser.id,
      quotaQps: values.quotaQps
    })
    message.success('QPS 配额已更新')
    setQuotaOpen(false)
    setSelectedUser(null)
    quotaForm.resetFields()
    loadUsers()
  }

  const handleDelete = async (userId) => {
    await userApi.delete({ userId })
    message.success('用户已删除')
    loadUsers()
  }

  const columns = [
    {
      title: '账号',
      dataIndex: 'userName',
      key: 'userName'
    },
    {
      title: 'QPS 配额',
      dataIndex: 'quotaQps',
      key: 'quotaQps'
    },
    {
      title: '管理员',
      dataIndex: 'isAdmin',
      key: 'isAdmin',
      render: (isAdmin) => <Tag color={isAdmin ? 'gold' : 'default'}>{isAdmin ? '是' : '否'}</Tag>
    },
    {
      title: '创建时间',
      dataIndex: 'createTime',
      key: 'createTime'
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openQuotaModal(record)}>
            调整 QPS
          </Button>
          <Popconfirm
            title="确定删除该用户吗？"
            okText="删除"
            cancelText="取消"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ]

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">账号列表</h2>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadUsers}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            添加用户
          </Button>
        </Space>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Input
          placeholder="输入用户名筛选"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          style={{ width: 320 }}
          allowClear
        />
      </div>

      <Table
        columns={columns}
        dataSource={filteredUsers}
        rowKey="id"
        loading={loading}
        pagination={{
          pageSize: 10,
          showSizeChanger: false
        }}
      />

      <Modal
        title="添加用户"
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => {
          setCreateOpen(false)
          createForm.resetFields()
        }}
      >
        <Form form={createForm} layout="vertical" initialValues={{ quotaQps: 10, isAdmin: false }}>
          <Form.Item
            name="userName"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="quotaQps"
            label="QPS 配额"
            rules={[{ required: true, message: '请输入 QPS 配额' }]}
          >
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="isAdmin" label="管理员" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={selectedUser ? `调整 ${selectedUser.userName} 的 QPS` : '调整 QPS'}
        open={quotaOpen}
        onOk={handleUpdateQuota}
        onCancel={() => {
          setQuotaOpen(false)
          setSelectedUser(null)
          quotaForm.resetFields()
        }}
      >
        <Form form={quotaForm} layout="vertical">
          <Form.Item
            name="quotaQps"
            label="QPS 配额"
            rules={[{ required: true, message: '请输入 QPS 配额' }]}
          >
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default UserList
