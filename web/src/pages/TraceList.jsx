import { useState, useEffect } from 'react'
import { Table, Card, Form, Input, Select, DatePicker, Button, Space, Tag, Typography, Divider } from 'antd'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import axios from 'axios'

const { Text } = Typography
const { RangePicker } = DatePicker

// 获取 API 基础路径
const getApiBase = () => {
  const host = window.location.hostname
  const port = window.location.port
  return `http://${host}:${port}/api`
}

function TraceList() {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState([])
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  })

  // 获取追踪列表
  const fetchTraces = async (params = {}) => {
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

      const response = await axios.get(`${getApiBase()}/traces`, { params: queryParams })

      if (response.data.code === 0) {
        setData(response.data.data || [])
        setPagination({
          current: params.current || 1,
          pageSize: params.pageSize || 20,
          total: response.data.total || 0,
        })
      }
    } catch (error) {
      console.error('获取追踪列表失败:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTraces()
  }, [])

  // 处理表格变化（分页、排序、筛选）
  const handleTableChange = (newPagination) => {
    fetchTraces({
      current: newPagination.current,
      pageSize: newPagination.pageSize,
    })
  }

  // 搜索
  const handleSearch = () => {
    fetchTraces({ current: 1, pageSize: pagination.pageSize })
  }

  // 重置
  const handleReset = () => {
    form.resetFields()
    fetchTraces({ current: 1, pageSize: pagination.pageSize })
  }

  // 查看追踪详情
  const viewTraceDetail = (traceId) => {
    window.open(`/trace/${traceId}`, '_blank')
  }

  // 表格列定义
  const columns = [
    {
      title: 'Trace ID',
      dataIndex: 'trace_id',
      key: 'trace_id',
      width: 280,
      render: (text) => (
        <Text copyable={{ text }} ellipsis style={{ width: 280 }}>
          {text}
        </Text>
      ),
    },
    {
      title: '分组',
      dataIndex: 'group',
      key: 'group',
      width: 120,
    },
    {
      title: '设备 ID',
      dataIndex: 'device_id',
      key: 'device_id',
      width: 150,
      render: (text) => text || '-',
    },
    {
      title: 'API',
      dataIndex: 'api',
      key: 'api',
      width: 200,
      ellipsis: true,
    },
    {
      title: '调用方',
      dataIndex: 'caller',
      key: 'caller',
      width: 130,
    },
    {
      title: '耗时 (ms)',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 100,
      sorter: true,
      render: (value) => {
        let color = 'green'
        if (value > 1000) color = 'red'
        else if (value > 500) color = 'orange'
        else if (value > 100) color = 'blue'
        return <Tag color={color}>{value} ms</Tag>
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (value) => {
        const color = value === 'SUCCESS' ? 'green' : 'red'
        return <Tag color={color}>{value}</Tag>
      },
    },
    {
      title: '开始时间',
      dataIndex: 'start_time',
      key: 'start_time',
      width: 180,
      sorter: true,
      render: (value) => value ? new Date(value).toLocaleString() : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <a onClick={() => viewTraceDetail(record.trace_id)}>详情</a>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>调用链路追踪</h2>
      </div>

      {/* 搜索表单 */}
      <Card style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline">
          <Form.Item name="traceId" label="Trace ID">
            <Input placeholder="输入 Trace ID" style={{ width: 280 }} allowClear />
          </Form.Item>

          <Form.Item name="group" label="分组">
            <Input placeholder="输入分组名称" allowClear />
          </Form.Item>

          <Form.Item name="deviceId" label="设备 ID">
            <Input placeholder="输入设备 ID" allowClear />
          </Form.Item>

          <Form.Item name="api" label="API">
            <Input placeholder="输入 API 路径" allowClear />
          </Form.Item>

          <Form.Item name="status" label="状态">
            <Select placeholder="请选择状态" allowClear style={{ width: 120 }}>
              <Select.Option value="SUCCESS">成功</Select.Option>
              <Select.Option value="FAILURE">失败</Select.Option>
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

      {/* 追踪列表表格 */}
      <Card>
        <Table
          columns={columns}
          dataSource={data}
          loading={loading}
          pagination={pagination}
          onChange={handleTableChange}
          rowKey="id"
          scroll={{ x: 1400 }}
        />
      </Card>
    </div>
  )
}

export default TraceList
