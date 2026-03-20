import { useState, useEffect } from 'react'
import { Table, Input, Button, Space, Popconfirm, message, Tag, Modal, Form, InputNumber } from 'antd'
import { SearchOutlined, PlusOutlined, EyeOutlined, DeleteOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { groupApi } from '../utils/api'

function GroupList() {
  const navigate = useNavigate()
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [createModalVisible, setCreateModalVisible] = useState(false)
  const [createForm] = Form.useForm()

  // 加载分组列表
  const loadGroups = async () => {
    setLoading(true)
    try {
      const result = await groupApi.list()
      setGroups(result.data || [])
    } catch (error) {
      // 如果是 401 错误，清除 token 并重定向到登录页
      if (error.response?.status === 401 || error.response?.status === 403) {
        localStorage.removeItem('api_token')
        localStorage.removeItem('login_token')
        window.location.href = '/login'
        return
      }
      message.error('加载分组列表失败：' + (error.message || '未知错误'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadGroups()
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
      title: '禁用客户端',
      dataIndex: 'disabledClients',
      key: 'disabledClients',
      render: (count) => <Tag color="red">{count}</Tag>
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

  const handleCreateGroup = () => {
    setCreateModalVisible(true)
    createForm.resetFields()
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
      setCreateModalVisible(false)
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

  const handleCreateModalCancel = () => {
    setCreateModalVisible(false)
    createForm.resetFields()
  }

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">分组列表</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateGroup}>
          创建分组
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
        dataSource={filteredGroups}
        rowKey="id"
        loading={loading}
        pagination={{
          current: 1,
          pageSize: 10,
          total: filteredGroups.length,
          showSizeChanger: false,
          showTotal: (total) => `共 ${total} 条`
        }}
      />

      <Modal
        title="创建分组"
        open={createModalVisible}
        onOk={handleCreateModalOk}
        onCancel={handleCreateModalCancel}
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
    </div>
  )
}

export default GroupList
