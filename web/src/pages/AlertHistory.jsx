import { useEffect, useState } from 'react'
import { Button, Card, DatePicker, Form, Input, Select, Space, Table, Tag } from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { alertApi } from '../utils/api'

const { RangePicker } = DatePicker

function AlertHistory() {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [histories, setHistories] = useState([])
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })

  const loadHistory = async (pageConfig = {}) => {
    setLoading(true)
    try {
      const fields = form.getFieldsValue()
      const params = {
        page: pageConfig.current || pagination.current,
        pageSize: pageConfig.pageSize || pagination.pageSize,
        ruleId: fields.ruleId,
        group: fields.group,
        level: fields.level
      }

      if (fields.timeRange?.length === 2) {
        params.startTime = fields.timeRange[0].format('YYYY-MM-DD HH:mm:ss')
        params.endTime = fields.timeRange[1].format('YYYY-MM-DD HH:mm:ss')
      }

      const result = await alertApi.getHistory(params)
      setHistories(result.data || [])
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
    loadHistory({ current: 1, pageSize: 20 })
  }, [])

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>告警历史</h2>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline">
          <Form.Item name="ruleId" label="规则 ID">
            <Input allowClear style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="group" label="分组">
            <Input allowClear />
          </Form.Item>
          <Form.Item name="level" label="级别">
            <Select allowClear style={{ width: 120 }}>
              <Select.Option value="INFO">INFO</Select.Option>
              <Select.Option value="WARNING">WARNING</Select.Option>
              <Select.Option value="CRITICAL">CRITICAL</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="timeRange" label="时间范围">
            <RangePicker showTime />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} onClick={() => loadHistory({ current: 1 })}>
                查询
              </Button>
              <Button
                icon={<ReloadOutlined />}
                onClick={() => {
                  form.resetFields()
                  loadHistory({ current: 1, pageSize: pagination.pageSize })
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
          dataSource={histories}
          pagination={pagination}
          onChange={(pager) => loadHistory({ current: pager.current, pageSize: pager.pageSize })}
          scroll={{ x: 1500 }}
          columns={[
            { title: '规则名称', dataIndex: 'ruleName', key: 'ruleName', width: 160, ellipsis: true },
            { title: '分组', dataIndex: 'group', key: 'group', width: 120, render: (value) => value || '-' },
            { title: 'API', dataIndex: 'api', key: 'api', width: 180, render: (value) => value || '-' },
            { title: '指标', dataIndex: 'metricName', key: 'metricName', width: 160 },
            { title: '当前值', dataIndex: 'currentValue', key: 'currentValue', width: 120, render: (value) => value?.toFixed?.(2) ?? value ?? '-' },
            { title: '阈值', dataIndex: 'threshold', key: 'threshold', width: 120, render: (value) => value?.toFixed?.(2) ?? value ?? '-' },
            { title: '操作符', dataIndex: 'operator', key: 'operator', width: 100 },
            {
              title: '级别',
              dataIndex: 'level',
              key: 'level',
              width: 110,
              render: (value) => {
                const colorMap = { INFO: 'blue', WARNING: 'orange', CRITICAL: 'red' }
                return <Tag color={colorMap[value] || 'default'}>{value}</Tag>
              }
            },
            { title: '已通知', dataIndex: 'notified', key: 'notified', width: 100, render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '是' : '否'}</Tag> },
            { title: '触发时间', dataIndex: 'triggeredAt', key: 'triggeredAt', width: 180 },
            { title: '消息', dataIndex: 'message', key: 'message', ellipsis: true }
          ]}
        />
      </Card>
    </div>
  )
}

export default AlertHistory
