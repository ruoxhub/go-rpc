import { useState, useEffect } from 'react'
import { Table, Input, Spin, Empty, Alert, Tag, Button, message, Modal, Form, InputNumber } from 'antd'
import { SearchOutlined, SyncOutlined, CheckCircleOutlined } from '@ant-design/icons'
import { anonymousGroupApi } from '../utils/api'

function AnonymousGroup() {
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [searchText, setSearchText] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [convertModalVisible, setConvertModalVisible] = useState(false)
  const [convertForm] = Form.useForm()

  // 加载匿名分组列表
  useEffect(() => {
    loadGroups()
  }, [])

  const loadGroups = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await anonymousGroupApi.list()
      // 兼容两种响应格式
      const data = Array.isArray(response) ? response : (response.data || [])
      setGroups(data)
    } catch (err) {
      // 错误已在 axios 拦截器中统一处理（401/403 跳转登录）
      // 此处仅设置错误信息显示在页面上
      setError(err.message || '加载失败')
      console.error('Failed to load anonymous groups:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleConvertGroup = (groupName) => {
    setConvertModalVisible(true)
    convertForm.setFieldsValue({
      groupName,
      quotaQpsGroup: 100,
      quotaQpsPerDevice: 10
    })
  }

  const handleConvertConfirm = async () => {
    try {
      const values = await convertForm.validateFields()
      await anonymousGroupApi.convert({
        groupName: values.groupName,
        quotaQpsGroup: values.quotaQpsGroup,
        quotaQpsPerDevice: values.quotaQpsPerDevice
      })
      message.success(`分组 ${values.groupName} 已转换为正式分组`)
      setConvertModalVisible(false)
      loadGroups()
    } catch (err) {
      // 错误已在拦截器中处理
      console.error('Failed to convert group:', err)
    }
  }

  const columns = [
    {
      title: '分组名称',
      dataIndex: 'groupName',
      key: 'groupName',
      sorter: (a, b) => a.groupName.localeCompare(b.groupName),
      render: (text) => <span style={{ fontWeight: 500 }}>{text}</span>
    },
    {
      title: '总设备数',
      dataIndex: 'totalClients',
      key: 'totalClients',
      align: 'center',
      sorter: (a, b) => a.totalClients - b.totalClients,
      render: (total) => <Tag color="blue">{total}</Tag>
    },
    {
      title: '可用客户端',
      dataIndex: 'availableClients',
      key: 'availableClients',
      align: 'center',
      sorter: (a, b) => a.availableClients - b.availableClients,
      render: (count) => (
        <Tag color="green" icon={<SyncOutlined spin />}>
          {count}
        </Tag>
      )
    },
    {
      title: '禁用客户端',
      dataIndex: 'disabledClients',
      key: 'disabledClients',
      align: 'center',
      sorter: (a, b) => a.disabledClients - b.disabledClients,
      render: (count) => (
        <Tag color="red">{count}</Tag>
      )
    },
    {
      title: '状态',
      key: 'status',
      align: 'center',
      render: (_, record) => {
        if (record.availableClients === 0 && record.disabledClients === 0) {
          return <Tag color="default">空分组</Tag>
        }
        if (record.availableClients > record.disabledClients) {
          return <Tag color="success">健康</Tag>
        }
        if (record.disabledClients > 0) {
          return <Tag color="warning">部分离线</Tag>
        }
        return <Tag color="default">正常</Tag>
      }
    },
    {
      title: '操作',
      key: 'action',
      align: 'center',
      render: (_, record) => (
        <Button
          type="primary"
          size="small"
          icon={<CheckCircleOutlined />}
          onClick={() => handleConvertGroup(record.groupName)}
        >
          转为正式分组
        </Button>
      )
    }
  ]

  const filteredGroups = groups.filter((group) =>
    group.groupName.toLowerCase().includes(searchText.toLowerCase())
  )

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">匿名分组</h2>
        <p className="page-description">
          匿名分组是指存在于设备列表中但未加入任何正式分组的设备
        </p>
      </div>

      {error && (
        <Alert
          message="加载失败"
          description={error}
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <div style={{ marginBottom: 16, display: 'flex', gap: 12 }}>
        <Input
          placeholder="请输入分组名称进行查询"
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => {
            setSearchText(e.target.value)
            setCurrentPage(1)
          }}
          style={{ width: 300 }}
          allowClear
        />
        <Button onClick={loadGroups} loading={loading} icon={<SyncOutlined />}>
          刷新
        </Button>
      </div>

      {loading ? (
        <Spin size="large" style={{ display: 'block', textAlign: 'center', marginTop: 60 }} />
      ) : filteredGroups.length === 0 ? (
        <Empty
          description={searchText ? '未找到匹配的分组' : '暂无匿名分组'}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        <Table
          columns={columns}
          dataSource={filteredGroups}
          rowKey="groupName"
          pagination={{
            current: currentPage,
            pageSize: pageSize,
            total: filteredGroups.length,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (page, size) => {
              setCurrentPage(page)
              setPageSize(size)
            }
          }}
        />
      )}

      {/* 转换确认对话框 */}
      <Modal
        title="将匿名分组转换为正式分组"
        open={convertModalVisible}
        onOk={handleConvertConfirm}
        onCancel={() => {
          setConvertModalVisible(false)
          convertForm.resetFields()
        }}
        okText="确认转换"
        cancelText="取消"
        width={500}
      >
        <Form
          form={convertForm}
          layout="vertical"
          initialValues={{
            quotaQpsGroup: 100,
            quotaQpsPerDevice: 10
          }}
        >
          <Form.Item
            name="groupName"
            label="分组名称"
            rules={[{ required: true, message: '请输入分组名称' }]}
          >
            <Input disabled placeholder="请输入分组名称" />
          </Form.Item>
          <Form.Item
            name="quotaQpsGroup"
            label="分组 QPS 限制"
            rules={[{ required: true, message: '请输入 QPS 限制' }]}
          >
            <InputNumber min={1} max={10000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="quotaQpsPerDevice"
            label="设备 QPS 限制"
            rules={[{ required: true, message: '请输入设备 QPS 限制' }]}
          >
            <InputNumber min={1} max={1000} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
        <Alert
          message="转换后将自动添加默认 Actions"
          description="系统将为该分组自动添加 invoke, execJs, getHtml, getCookie 四个默认 Action"
          type="info"
          showIcon
          style={{ marginTop: 16 }}
        />
      </Modal>
    </div>
  )
}

export default AnonymousGroup
