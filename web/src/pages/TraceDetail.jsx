import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Card, Descriptions, Table, Spin, Alert, Typography, Divider, Tag } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import axios from 'axios'

const { Text, Title } = Typography

// 获取 API 基础路径
const getApiBase = () => {
  const host = window.location.hostname
  const port = window.location.port
  return `http://${host}:${port}/api`
}

function TraceDetail() {
  const { traceId } = useParams()
  const [loading, setLoading] = useState(true)
  const [traceData, setTraceData] = useState(null)
  const [spans, setSpans] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchTraceDetail = async () => {
      try {
        const response = await axios.get(`${getApiBase()}/traces/${traceId}`)

        if (response.data.code === 0) {
          setTraceData(response.data.data)
          setSpans(response.data.data?.spans || [])
        } else {
          setError(response.data.message || '加载失败')
        }
      } catch (err) {
        setError('加载追踪详情失败：' + err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchTraceDetail()
  }, [traceId])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 60 }}>
        <Spin size="large" tip="加载中..." />
      </div>
    )
  }

  if (error) {
    return (
      <Alert
        type="error"
        message="加载失败"
        description={error}
        showIcon
      />
    )
  }

  if (!traceData) {
    return (
      <Alert
        type="warning"
        message="未找到追踪记录"
        description={
          <div>
            <Link to="/traces">
              <ArrowLeftOutlined /> 返回追踪列表
            </Link>
          </div>
        }
        showIcon
      />
    )
  }

  // Span 表格列定义
  const spanColumns = [
    {
      title: 'Span ID',
      dataIndex: 'span_id',
      key: 'span_id',
      width: 200,
      render: (text) => (
        <Text copyable={{ text }} ellipsis style={{ width: 200 }}>
          {text}
        </Text>
      ),
    },
    {
      title: '父 Span',
      dataIndex: 'parent_span_id',
      key: 'parent_span_id',
      width: 200,
      render: (text) => text || '-',
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
    },
    {
      title: 'API',
      dataIndex: 'api',
      key: 'api',
      ellipsis: true,
    },
    {
      title: '耗时 (ms)',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 100,
      render: (value) => {
        let color = 'green'
        if (value > 1000) color = 'red'
        else if (value > 500) color = 'orange'
        return <Tag color={color}>{value}</Tag>
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
      title: '错误信息',
      dataIndex: 'error_message',
      key: 'error_message',
      ellipsis: true,
      render: (text) => text || '-',
    },
    {
      title: '开始时间',
      dataIndex: 'start_time',
      key: 'start_time',
      width: 180,
      render: (value) => value ? new Date(value).toLocaleString() : '-',
    },
  ]

  return (
    <div>
      {/* 返回链接 */}
      <div style={{ marginBottom: 16 }}>
        <Link to="/traces">
          <ArrowLeftOutlined /> 返回追踪列表
        </Link>
      </div>

      {/* 追踪概要信息 */}
      <Card title="追踪概要" style={{ marginBottom: 16 }}>
        <Descriptions column={2} bordered>
          <Descriptions.Item label="Trace ID">
            <Text copyable>{traceData.trace_id}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="Span 数量">
            {spans.length}
          </Descriptions.Item>
          <Descriptions.Item label="分组">
            {spans[0]?.group || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="设备 ID">
            {spans[0]?.device_id || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="API">
            {spans[0]?.api || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="总耗时 (ms)">
            {spans[0]?.duration_ms || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="开始时间">
            {spans[0]?.start_time ? new Date(spans[0].start_time).toLocaleString() : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            {spans[0]?.status === 'SUCCESS' ? (
              <Tag color="green">成功</Tag>
            ) : (
              <Tag color="red">失败</Tag>
            )}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Span 列表 */}
      <Card title="Span 列表">
        <Table
          columns={spanColumns}
          dataSource={spans}
          rowKey="id"
          pagination={false}
          scroll={{ x: 1600 }}
        />
      </Card>
    </div>
  )
}

export default TraceDetail
