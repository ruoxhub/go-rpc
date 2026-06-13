import { useState, useEffect } from 'react'
import { Table, Input, Button, Space, Popconfirm, message, Tag, Modal, Form, InputNumber } from 'antd'
import { SearchOutlined, PlusOutlined, EyeOutlined, DeleteOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { groupApi } from '../utils/api'

const { TextArea } = Input

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
      title: 'IP 白名单',
      dataIndex: 'allowedIps',
      key: 'allowedIps',
      render: (raw) => {
        const list = (raw || '').split(',').map((s) => s.trim()).filter(Boolean)
        if (list.length === 0) return <Tag>公开</Tag>
        if (list.length <= 2) {
          return (
            <Space wrap size={[4, 4]}>
              {list.map((ip) => <Tag key={ip} color="blue">{ip}</Tag>)}
            </Space>
          )
        }
        return (
          <Space wrap size={[4, 4]}>
            <Tag color="blue">{list[0]}</Tag>
            <Tag color="blue">+{list.length - 1}</Tag>
          </Space>
        )
      }
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
        quotaQpsPerDevice: values.quotaQpsPerDevice || -1,
        allowedIps: (values.allowedIps || '').trim()
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
          <Form.Item
            name="allowedIps"
            label={<Space size={4}><LockOutlined />IP 白名单（可选）</Space>}
            extra="留空表示不启用；精确 IP 或 CIDR，多项逗号分隔"
            rules={[
              {
                validator: (_, value) => {
                  const entries = (value || '').split(',').map((s) => s.trim()).filter(Boolean)
                  const ipRe = /^[\da-fA-F.:]+$/
                  const cidrRe = /^[\da-fA-F.:]+\/\d+$/
                  for (const e of entries) {
                    if (!ipRe.test(e) && !cidrRe.test(e)) {
                      return Promise.reject(new Error(`非法条目：${e}`))
                    }
                  }
                  return Promise.resolve()
                }
              }
            ]}
          >
            <TextArea rows={2} placeholder="例如：10.0.0.0/8, 203.0.113.5" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default GroupList
