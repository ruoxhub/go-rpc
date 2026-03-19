import { useState } from 'react'
import { Table, Input, Space, Tag, Button, Popconfirm, message } from 'antd'
import { SearchOutlined, DeleteOutlined, ExclamationCircleOutlined } from '@ant-design/icons'

// 模拟数据
const mockDevices = [
  {
    id: '0.7338219124976066',
    deviceIp: '127.0.0.1',
    registerTime: '2026-03-19T08:38:45',
    lastActiveTime: '2026-03-19T19:53:27',
    status: 'online'
  },
  {
    id: '0.9951795669479898',
    deviceIp: '172.21.0.1',
    registerTime: '2026-03-19T08:38:45',
    lastActiveTime: '2026-03-19T08:58:45',
    status: 'offline'
  },
  {
    id: '0.6075113234751223',
    deviceIp: '172.21.0.1',
    registerTime: '2026-03-18T12:18:32',
    lastActiveTime: '2026-03-19T00:16:13',
    status: 'offline'
  }
]

function GroupDeviceList({ groupName }) {
  const [devices] = useState(mockDevices)
  const [searchText, setSearchText] = useState('')

  const columns = [
    {
      title: '分组',
      dataIndex: 'groupName',
      key: 'groupName',
      render: () => groupName
    },
    {
      title: '设备 ID',
      dataIndex: 'id',
      key: 'id'
    },
    {
      title: '设备 ip',
      dataIndex: 'deviceIp',
      key: 'deviceIp'
    },
    {
      title: '注册时间',
      dataIndex: 'registerTime',
      key: 'registerTime'
    },
    {
      title: '最后活跃时间',
      dataIndex: 'lastActiveTime',
      key: 'lastActiveTime'
    },
    {
      title: '设备状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => (
        <Tag color={status === 'online' ? 'green' : 'red'}>
          {status}
        </Tag>
      )
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Popconfirm
            title="确定删除该设备吗？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
          {record.status === 'online' && (
            <Button size="small" icon={<ExclamationCircleOutlined />}>
              移除可用队列
            </Button>
          )}
        </Space>
      )
    }
  ]

  const filteredDevices = devices.filter((device) =>
    device.id.toLowerCase().includes(searchText.toLowerCase()) ||
    device.deviceIp.toLowerCase().includes(searchText.toLowerCase())
  )

  const handleDelete = (id) => {
    // TODO: 调用 API 删除设备
    message.success('设备删除成功')
  }

  return (
    <div>
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
        dataSource={filteredDevices}
        rowKey="id"
        pagination={{
          current: 1,
          pageSize: 10,
          total: filteredDevices.length,
          showSizeChanger: false,
          showTotal: (total) => `共 ${total} 条`
        }}
      />
    </div>
  )
}

export default GroupDeviceList
