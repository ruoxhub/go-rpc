import { useState, useEffect } from 'react'
import { Card, Table, Form, Input, Select, DatePicker, Button, Space, Tag, Typography } from 'antd'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import axios from 'axios'

const { Option } = Select
const { RangePicker } = DatePicker
const { Text } = Typography

// 获取 API 基础路径
const getApiBase = () => {
  const host = window.location.hostname
  const port = window.location.port
  return `http://${host}:${port}/api`
}

function AlertHistory() {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [histories, setHistories] = useState([])
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  })

  // 获取告警历史列表
  const fetchHistories = async (params = {}) => {
    setLoading(true)
    try {
      const queryParams = {
        page: params.current || 1,
        pageSize: params.pageSize || 20,
        ...form.getFieldsValue(),
      }

      // 处理时间范围
      if (queryParams.timeRange && Array.isArray(queryParams.timeRange)) {
        queryParams.startTime = queryParams.timeRange[0].format('YYYY-MM-DD HH:mm:ss')
        queryParams.endTime = queryParams.timeRange[1].format('YYYY-MM-DD HH:mm:ss')
        delete queryParams.timeRange
      }

      const response = await axios.get(`${getApiBase()}/alerts/history`, { params: queryParams })

      if (response.data.code === 0) {
        setHistories(response.data.data || [])
        setPagination({
          current: params.current || 1,
          pageSize: params.pageSize || 20,
          total: response.data.total || 0,
        })
      }
    } catch (error) {
      console.error('获取告警历史失败:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchHistories()
  }, [])

  // 搜索
  const handleSearch = () => {
    fetchHistories({ current: 1, pageSize: pagination.pageSize })
  }

  // 重置
  const handleReset = () => {
    form.resetFields()
    fetchHistories({ current: 1, pageSize: pagination.pageSize })
  }

  // 表格变化
  const handleTableChange = (newPagination) => {
    fetchHistories({
      current: newPagination.current,
      pageSize: newPagination.pageSize,
    })
  }

  // 获取级别颜色
  const getLevelColor = (level) => {
    switch (level) {
      case 'INFO': return 'blue'
      case 'WARNING': return 'orange'
      case 'CRITICAL': return 'red'
      default: return 'default'
    }
  }

  // 表格列定义
  const columns = [
    {
      title: '规则名称',
      dataIndex: 'ruleName',
      key: 'ruleName',
      width: 150,
      ellipsis: true,
    },
    {
      title: '分组',
      dataIndex: 'group',
      key: 'group',
      width: 120,
      render: (text) => text || '-',
    },
    {
      title: 'API',
      dataIndex: 'api',
      key: 'api',
      width: 120,
      ellipsis: true,
      render: (text) => text || '-',
    },
    {
      title: '指标',
      dataIndex: 'metricName',
      key: 'metricName',
      width: 150,
      ellipsis: true,
    },
    {
      title: '当前值',
      dataIndex: 'currentValue',
      key: 'currentValue',
      width: 100,
      render: (value) => value?.toFixed(2) || '-',
    },
    {
      title: '阈值',
      dataIndex: 'threshold',
      key: 'threshold',
      width: 100,
      render: (value) => value?.toFixed(2) || '-',
    },
    {
      title: '条件',
      key: 'condition',
      width: 100,
      render: (_, record) => (
        <span>
          {record.operator} {record.threshold?.toFixed(2)}
        </span>
      ),
    },
    {
      title: '级别',
      dataIndex: 'level',
      key: 'level',
      width: 90,
      render: (level) => (
        <Tag color={getLevelColor(level)}>{level}</Tag>
      ),
    },
    {
      title: '已通知',
      dataIndex: 'notified',
      key: 'notified',
      width: 80,
      render: (notified) => (
        <Tag color={notified ? 'green' : 'default'}>
          {notified ? '是' : '否'}
        </Tag>
      ),
    },
    {
      title: '触发时间',
      dataIndex: 'triggeredAt',
      key: 'triggeredAt',
      width: 160,
    },
    {
      title: '消息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
      render: (text) => (
        <Text copyable={{ text }}>{text}</Text>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>告警历史</h2>
      </div>

      {/* 搜索表单 */}
      <Card style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline">
          <Form.Item name="ruleId" label="规则 ID">
            <Input type="number" placeholder="输入规则 ID" style={{ width: 120 }} allowClear />
          </Form.Item>

          <Form.Item name="group" label="分组">
            <Input placeholder="输入分组名称" allowClear style={{ width: 150 }} />
          </Form.Item>

          <Form.Item name="level" label="级别">
            <Select placeholder="请选择级别" allowClear style={{ width: 120 }}>
              <Option value="INFO">INFO</Option>
              <Option value="WARNING">WARNING</Option>
              <Option value="CRITICAL">CRITICAL</Option>
            </Select>
          </Form.Item>

          <Form.Item name="timeRange" label="时间范围">
            <RangePicker />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
                查询
              </Button>
              <Button icon={<ReloadOutlined />} onClick={handleReset}>
                重置
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {/* 告警历史表格 */}
      <Card>
        <Table
          columns={columns}
          dataSource={histories}
          loading={loading}
          pagination={pagination}
          onChange={handleTableChange}
          rowKey="id"
          scroll={{ x: 1600 }}
        />
      </Card>
    </div>
  )
}

export default AlertHistory
