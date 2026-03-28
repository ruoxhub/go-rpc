import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Alert, Card, Descriptions, Table, Tag } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { traceApi } from '../utils/api'

function TraceDetail() {
  const { traceId } = useParams()
  const [loading, setLoading] = useState(true)
  const [traceData, setTraceData] = useState(null)
  const [extraData, setExtraData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError('')
      try {
        const [detail, extra] = await Promise.all([
          traceApi.getTraceDetail(traceId),
          traceApi.getTraceExtraData(traceId).catch(() => ({ data: null }))
        ])
        setTraceData(detail.data)
        setExtraData(extra.data || null)
      } catch (err) {
        setError(err.response?.data?.message || err.message || '加载追踪详情失败')
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [traceId])

  if (error) {
    return <Alert type="error" showIcon message="加载失败" description={error} />
  }

  const spans = traceData?.spans || []
  const rootSpan = spans[0]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Link to="/traces">
          <ArrowLeftOutlined /> 返回追踪列表
        </Link>
      </div>

      <Card loading={loading} title="追踪概览" style={{ marginBottom: 16 }}>
        {traceData && (
          <Descriptions column={2} bordered>
            <Descriptions.Item label="Trace ID">{traceData.trace_id}</Descriptions.Item>
            <Descriptions.Item label="Span 数量">{spans.length}</Descriptions.Item>
            <Descriptions.Item label="分组">{rootSpan?.group || '-'}</Descriptions.Item>
            <Descriptions.Item label="设备 ID">{rootSpan?.device_id || '-'}</Descriptions.Item>
            <Descriptions.Item label="API">{rootSpan?.api || '-'}</Descriptions.Item>
            <Descriptions.Item label="调用方">{rootSpan?.caller || '-'}</Descriptions.Item>
            <Descriptions.Item label="开始时间">
              {rootSpan?.start_time ? new Date(rootSpan.start_time).toLocaleString() : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={rootSpan?.status === 'SUCCESS' ? 'green' : 'red'}>
                {rootSpan?.status || '-'}
              </Tag>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Card>

      {extraData && (
        <Card loading={loading} title="附加信息" style={{ marginBottom: 16 }}>
          <Descriptions column={2} bordered>
            <Descriptions.Item label="请求方法">{extraData.method || '-'}</Descriptions.Item>
            <Descriptions.Item label="Content-Type">{extraData.content_type || '-'}</Descriptions.Item>
            <Descriptions.Item label="User-Agent">{extraData.user_agent || '-'}</Descriptions.Item>
            <Descriptions.Item label="状态码">{extraData.status_code ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="用户 ID">{extraData.user_id ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="用户名">{extraData.user_name || '-'}</Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      <Card loading={loading} title="Span 列表">
        <Table
          rowKey="id"
          dataSource={spans}
          pagination={false}
          scroll={{ x: 1500 }}
          columns={[
            { title: 'Span ID', dataIndex: 'span_id', key: 'span_id', width: 220 },
            { title: '父 Span', dataIndex: 'parent_span_id', key: 'parent_span_id', width: 220, render: (value) => value || '-' },
            { title: '分组', dataIndex: 'group', key: 'group', width: 120 },
            { title: '设备 ID', dataIndex: 'device_id', key: 'device_id', width: 160, render: (value) => value || '-' },
            { title: 'API', dataIndex: 'api', key: 'api', width: 220, ellipsis: true },
            { title: '耗时', dataIndex: 'duration_ms', key: 'duration_ms', width: 100, render: (value) => `${value} ms` },
            { title: '状态', dataIndex: 'status', key: 'status', width: 110, render: (value) => <Tag color={value === 'SUCCESS' ? 'green' : 'red'}>{value}</Tag> },
            { title: '错误信息', dataIndex: 'error_message', key: 'error_message', ellipsis: true, render: (value) => value || '-' },
            { title: '开始时间', dataIndex: 'start_time', key: 'start_time', width: 180, render: (value) => (value ? new Date(value).toLocaleString() : '-') }
          ]}
        />
      </Card>
    </div>
  )
}

export default TraceDetail
