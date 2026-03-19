import { useState } from 'react'
import { Table, Input, Button, Space, Popconfirm, message, Modal, Form } from 'antd'
import { SearchOutlined, PlusOutlined, EditOutlined, DeleteOutlined, SafetyOutlined, UserOutlined } from '@ant-design/icons'

// 模拟数据
const mockUsers = [
  {
    id: 1,
    userName: 'ruoxing',
    password: 'mrx123456',
    quotaQps: 10,
    isAdmin: true,
    permission: 'all'
  }
]

function UserList() {
  const [users] = useState(mockUsers)
  const [searchText, setSearchText] = useState('')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [form] = Form.useForm()

  const columns = [
    {
      title: '账号',
      dataIndex: 'userName',
      key: 'userName'
    },
    {
      title: '密码',
      dataIndex: 'password',
      key: 'password'
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
      render: (isAdmin) => (isAdmin ? '是' : '否')
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<SafetyOutlined />}>
            登录
          </Button>
          <Button size="small" icon={<UserOutlined />}>
            配置权限
          </Button>
          <Button size="small" icon={<SafetyOutlined />}>
            移除管理员
          </Button>
          <Button size="small" icon={<EditOutlined />}>
            QPS 配额
          </Button>
        </Space>
      )
    }
  ]

  const filteredUsers = users.filter((user) =>
    user.userName.toLowerCase().includes(searchText.toLowerCase())
  )

  const handleAddUser = () => {
    setIsModalOpen(true)
  }

  const handleModalOk = () => {
    form.submit()
  }

  const handleModalCancel = () => {
    setIsModalOpen(false)
  }

  const onFinish = (values) => {
    // TODO: 调用 API 添加用户
    console.log('添加用户:', values)
    message.success('用户添加成功')
    setIsModalOpen(false)
    form.resetFields()
  }

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">账号列表</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAddUser}>
          添加用户
        </Button>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Input
          placeholder="请输入关键词进行查询"
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          style={{ width: 300 }}
        />
      </div>

      <Table
        columns={columns}
        dataSource={filteredUsers}
        rowKey="id"
        pagination={{
          current: 1,
          pageSize: 10,
          total: filteredUsers.length,
          showSizeChanger: false,
          showTotal: (total) => `共 ${total} 条`
        }}
      />

      <Modal
        title="添加用户"
        open={isModalOpen}
        onOk={handleModalOk}
        onCancel={handleModalCancel}
      >
        <Form form={form} layout="vertical" onFinish={onFinish}>
          <Form.Item
            name="userName"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="请输入用户名" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password placeholder="请输入密码" />
          </Form.Item>
          <Form.Item
            name="quotaQps"
            label="QPS 配额"
            initialValue={10}
          >
            <Input type="number" />
          </Form.Item>
          <Form.Item
            name="isAdmin"
            label="管理员"
            valuePropName="checked"
            initialValue={false}
          >
            <Input type="checkbox" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default UserList
