import { useState, useEffect } from 'react'
import { Table, Input, Space, Tag, Button, Popconfirm, message } from 'antd'
import { SearchOutlined, DeleteOutlined, ExclamationCircleOutlined } from '@ant-design/icons'
import { groupApi } from '../utils/api'

function GroupDeviceList({ groupName, onRefresh }) {
  const [devices, setDevices] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchText, setSearchText] = useState('')

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
            onConfirm={() => handleDelete(record.deviceId)}
            okText="确定"
            cancelText="取消"
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
          {record.status === 'online' && (
            <Popconfirm
              title="确定将该设备移出可用队列吗？"
              onConfirm={() => handleDisable(record.deviceId)}
              okText="确定"
              cancelText="取消"
            >
              <Button size="small" icon={<ExclamationCircleOutlined />}>
                移除可用
              </Button>
            </Popconfirm>
          )}
        </Space>
      )
    }
  ]

  const filteredDevices = devices.filter((device) =>
    device.deviceId.toLowerCase().includes(searchText.toLowerCase()) ||
    device.deviceIp.toLowerCase().includes(searchText.toLowerCase())
  )

  const handleDelete = async (deviceId) => {
    try {
      await groupApi.deleteDevice({ groupName, deviceId })
      message.success('设备删除成功')
      loadDevices()
      onRefresh && onRefresh()
    } catch (error) {
      message.error('删除设备失败：' + (error.message || '未知错误'))
    }
  }

  const handleDisable = async (deviceId) => {
    try {
      await groupApi.disableDevice({ groupName, deviceId, disable: true })
      message.success('设备已移出可用队列')
      loadDevices()
      onRefresh && onRefresh()
    } catch (error) {
      message.error('操作失败：' + (error.message || '未知错误'))
    }
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
        rowKey="deviceId"
        loading={loading}
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
