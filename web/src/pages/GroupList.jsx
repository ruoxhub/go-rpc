import { useState } from 'react'
import { Table, Input, Button, Space, Popconfirm, message, Tag } from 'antd'
import { SearchOutlined, PlusOutlined, EyeOutlined, DeleteOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

// 模拟数据
const mockGroups = [
  {
    id: 1,
    groupName: 'github',
    userName: 'ruoxing',
    quotaQpsGroup: 10,
    quotaQpsPerDevice: 100,
    createTime: '2026-03-19T19:44:01',
    availableClients: 1,
    disabledClients: 0
  }
]

function GroupList() {
  const navigate = useNavigate()
  const [groups] = useState(mockGroups)
  const [searchText, setSearchText] = useState('')

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
      key: 'availableClients'
    },
    {
      title: '禁用客户端',
      dataIndex: 'disabledClients',
      key: 'disabledClients'
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
            onConfirm={() => handleDelete(record.id)}
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

  const handleDelete = (id) => {
    // TODO: 调用 API 删除分组
    message.success('分组删除成功')
  }

  const handleCreateGroup = () => {
    // TODO: 打开创建分组对话框
    message.info('创建分组功能待实现')
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
        pagination={{
          current: 1,
          pageSize: 10,
          total: filteredGroups.length,
          showSizeChanger: false,
          showTotal: (total) => `共 ${total} 条`
        }}
      />
    </div>
  )
}

export default GroupList
