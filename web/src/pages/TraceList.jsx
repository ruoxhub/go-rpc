import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, DatePicker, Form, Input, Select, Space, Table, Tag, Typography } from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { traceApi } from '../utils/api'

const { RangePicker } = DatePicker
const { Text } = Typography

function TraceList() {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState([])
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0
  })

  const fetchTraces = async (pageConfig = {}) => {
    setLoading(true)
    try {
      const fields = form.getFieldsValue()
      const params = {
        page: pageConfig.current || pagination.current,
        pageSize: pageConfig.pageSize || pagination.pageSize,
        traceId: fields.traceId,
        group: fields.group,
        deviceId: fields.deviceId,
        api: fields.api,
        status: fields.status
      }

      if (fields.timeRange?.length === 2) {
        params.startTime = fields.timeRange[0].format('YYYY-MM-DD HH:mm:ss')
        params.endTime = fields.timeRange[1].format('YYYY-MM-DD HH:mm:ss')
      }

      const result = await traceApi.getTraces(params)
      setData(result.data || [])
      setPagination({
        current: params.page,
        pageSize: params.pageSize,
        total: result.total || 0
      })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTraces({ current: 1, pageSize: 20 })
  }, [])

  const columns = [
    {
      title: 'Trace ID',
      dataIndex: 'trace_id',
      key: 'trace_id',
      width: 280,
      render: (value) => (
        <Text copyable={{ text: value }} ellipsis style={{ width: 260 }}>
          {value}
        </Text>
      )
    },
    {
      title: '分组',
      dataIndex: 'group',
      key: 'group',
      width: 140
    },
    {
      title: '设备 ID',
      dataIndex: 'device_id',
      key: 'device_id',
      width: 160,
      render: (value) => value || '-'
    },
    {
      title: 'API',
      dataIndex: 'api',
      key: 'api',
      width: 220,
      ellipsis: true
    },
    {
      title: '调用方',
      dataIndex: 'caller',
      key: 'caller',
      width: 140,
      render: (value) => value || '-'
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 120,
      render: (value) => {
        let color = 'green'
        if (value > 1000) color = 'red'
        else if (value > 500) color = 'orange'
        else if (value > 100) color = 'blue'
        return <Tag color={color}>{value} ms</Tag>
      }
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (value) => <Tag color={value === 'SUCCESS' ? 'green' : 'red'}>{value}</Tag>
    },
    {
      title: '开始时间',
      dataIndex: 'start_time',
      key: 'start_time',
      width: 180,
      render: (value) => (value ? new Date(value).toLocaleString() : '-')
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <a onClick={() => navigate(`/traces/${record.trace_id}`)}>详情</a>
      )
    }
  ]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>调用链路追踪</h2>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline">
          <Form.Item name="traceId" label="Trace ID">
            <Input allowClear style={{ width: 260 }} />
          </Form.Item>
          <Form.Item name="group" label="分组">
            <Input allowClear />
          </Form.Item>
          <Form.Item name="deviceId" label="设备 ID">
            <Input allowClear />
          </Form.Item>
          <Form.Item name="api" label="API">
            <Input allowClear />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select allowClear style={{ width: 120 }}>
              <Select.Option value="SUCCESS">SUCCESS</Select.Option>
              <Select.Option value="FAILURE">FAILURE</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="timeRange" label="时间范围">
            <RangePicker showTime />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} onClick={() => fetchTraces({ current: 1 })}>
                查询
              </Button>
              <Button
                icon={<ReloadOutlined />}
                onClick={() => {
                  form.resetFields()
                  fetchTraces({ current: 1, pageSize: pagination.pageSize })
                }}
              >
                重置
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      <Card>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={data}
          pagination={pagination}
          onChange={(pager) => fetchTraces({ current: pager.current, pageSize: pager.pageSize })}
          scroll={{ x: 1500 }}
        />
      </Card>
    </div>
  )
}

export default TraceList
