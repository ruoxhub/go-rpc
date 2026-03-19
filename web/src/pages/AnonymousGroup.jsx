import { useState } from 'react'
import { Table, Input, Space, Button, Tag, Popconfirm, message } from 'antd'
import { SearchOutlined, DeleteOutlined, ExclamationCircleOutlined } from '@ant-design/icons'

// 模拟数据
const mockAnonymousGroups = [
  {
    id: 1,
    groupName: 'youtube',
    availableClients: 1,
    disabledClients: 0
  }
]

function AnonymousGroup() {
  const [groups] = useState(mockAnonymousGroups)
  const [searchText, setSearchText] = useState('')

  const columns = [
    {
      title: '分组',
      dataIndex: 'groupName',
      key: 'groupName'
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
    }
  ]

  const filteredGroups = groups.filter((group) =>
    group.groupName.toLowerCase().includes(searchText.toLowerCase())
  )

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">匿名分组</h2>
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

export default AnonymousGroup
