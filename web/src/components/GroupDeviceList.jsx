import { useState, useEffect } from 'react'
import { Table, Input, Space, Button, Popconfirm, message } from 'antd'
import { SearchOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import { groupApi } from '../utils/api'

function GroupDeviceList({ groupName, onRefresh }) {
  const [devices, setDevices] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)

  // 加载设备列表
  const loadDevices = async () => {
    setLoading(true)
    try {
      const result = await groupApi.getDevices(groupName)
      setDevices(result.data || [])
    } catch (error) {
      message.error('加载设备列表失败：' + (error.message || '未知错误'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDevices()
  }, [groupName])

  const columns = [
    {
      title: '分组',
      dataIndex: 'groupName',
      key: 'groupName',
      render: () => groupName
    },
    {
      title: '设备 ID',
      dataIndex: 'deviceId',
      key: 'deviceId'
    },
    {
      title: '设备 IP',
      dataIndex: 'deviceIp',
      key: 'deviceIp',
      render: (ip) => ip || '-'
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
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Popconfirm
            title="确定下线/剔除该设备吗？"
            onConfirm={() => handleDelete(record.deviceId)}
            okText="确定"
            cancelText="取消"
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              剔除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ]

  const handleDelete = async (deviceId) => {
    try {
      await groupApi.deleteDevice({ groupName, deviceId })
      message.success('设备已剔除')
      loadDevices()
      onRefresh && onRefresh()
    } catch (error) {
      message.error('剔除设备失败：' + (error.message || '未知错误'))
    }
  }

  const filteredDevices = devices.filter((device) => {
    const matchesSearch =
      (device.deviceId?.toLowerCase() || '').includes(searchText.toLowerCase()) ||
      (device.deviceIp?.toLowerCase() || '').includes(searchText.toLowerCase())
    return matchesSearch
  })

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <Input
          placeholder="请输入关键词进行查询"
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => {
            setSearchText(e.target.value)
            setCurrentPage(1)
          }}
          style={{ width: 260 }}
          allowClear
        />

        <Button icon={<ReloadOutlined />} onClick={loadDevices} loading={loading}>
          刷新
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={filteredDevices}
        rowKey="deviceId"
        loading={loading}
        pagination={{
          current: currentPage,
          pageSize: pageSize,
          total: filteredDevices.length,
          showSizeChanger: true,
          showQuickJumper: true,
          onChange: (page, size) => {
            setCurrentPage(page)
            setPageSize(size)
          },
          showTotal: (total) => `共 ${total} 台在线设备`
        }}
      />
    </div>
  )
}

export default GroupDeviceList
