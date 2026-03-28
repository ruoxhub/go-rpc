import { useEffect, useState } from 'react'
import { Button, Card, Form, Input, Modal, Table, Tabs, Tag, message } from 'antd'
import { EditOutlined, ReloadOutlined } from '@ant-design/icons'
import { sysConfigApi } from '../utils/api'

function SystemPanel() {
  const [configForm] = Form.useForm()
  const [configs, setConfigs] = useState([])
  const [nodes, setNodes] = useState([])
  const [sysLogs, setSysLogs] = useState([])
  const [appLogs, setAppLogs] = useState([])
  const [activeTab, setActiveTab] = useState('config')
  const [loading, setLoading] = useState(false)
  const [editTarget, setEditTarget] = useState(null)

  const loadAll = async () => {
    setLoading(true)
    try {
      const [configResult, nodeResult, sysLogResult, appLogResult] = await Promise.all([
        sysConfigApi.list(),
        sysConfigApi.getNodes(),
        sysConfigApi.getLogs({ page: 1, pageSize: 20 }),
        sysConfigApi.getAppLogs({ page: 1, pageSize: 20 })
      ])
      setConfigs(configResult.data || [])
      setNodes(nodeResult.data || [])
      setSysLogs(sysLogResult.data || [])
      setAppLogs(appLogResult.data || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [])

  const tabItems = [
    {
      key: 'config',
      label: '系统设置',
      children: (
        <Card loading={loading}>
          <Table
            rowKey="key"
            dataSource={configs}
            pagination={false}
            columns={[
              { title: '配置项', dataIndex: 'label', key: 'label', width: 320 },
              { title: '配置键', dataIndex: 'key', key: 'key', width: 280 },
              { title: '配置值', dataIndex: 'value', key: 'value', render: (value) => value || '-' },
              {
                title: '操作',
                key: 'action',
                width: 120,
                render: (_, record) => (
                  <Button
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => {
                      setEditTarget(record)
                      configForm.setFieldsValue({ value: record.value })
                    }}
                  >
                    编辑
                  </Button>
                )
              }
            ]}
          />
        </Card>
      )
    },
    {
      key: 'nodes',
      label: '服务节点',
      children: (
        <Card loading={loading}>
          <Table
            rowKey="id"
            dataSource={nodes}
            pagination={false}
            columns={[
              { title: '服务 ID', dataIndex: 'server_id', key: 'server_id', width: 220 },
              { title: 'IP', dataIndex: 'ip', key: 'ip', width: 180 },
              { title: '端口', dataIndex: 'port', key: 'port', width: 100 },
              { title: '本地 IP', dataIndex: 'local_ip', key: 'local_ip', width: 180, render: (value) => value || '-' },
              { title: '出口 IP', dataIndex: 'out_ip', key: 'out_ip', width: 180, render: (value) => value || '-' },
              { title: '状态', dataIndex: 'enable', key: 'enable', width: 100, render: (value) => <Tag color={value ? 'green' : 'red'}>{value ? '启用' : '禁用'}</Tag> },
              { title: '最后活跃时间', dataIndex: 'last_active_time', key: 'last_active_time', render: (value) => (value ? new Date(value).toLocaleString() : '-') }
            ]}
          />
        </Card>
      )
    },
    {
      key: 'logs',
      label: '系统日志',
      children: (
        <Card loading={loading}>
          <Table
            rowKey="id"
            dataSource={sysLogs}
            pagination={false}
            columns={[
              { title: '用户', dataIndex: 'username', key: 'username', width: 140, render: (value) => value || '-' },
              { title: '操作', dataIndex: 'operation', key: 'operation', width: 220, render: (value) => value || '-' },
              { title: '方法', dataIndex: 'method_name', key: 'method_name', width: 220, render: (value) => value || '-' },
              { title: '参数', dataIndex: 'params', key: 'params', ellipsis: true, render: (value) => value || '-' },
              { title: '时间', dataIndex: 'create_time', key: 'create_time', width: 180, render: (value) => (value ? new Date(value).toLocaleString() : '-') }
            ]}
          />
        </Card>
      )
    },
    {
      key: 'app-logs',
      label: '应用日志',
      children: (
        <Card loading={loading}>
          <Table
            rowKey={(record, index) => `${record.trace_id || 'log'}-${index}`}
            dataSource={appLogs}
            pagination={false}
            columns={[
              { title: '时间', dataIndex: 'timestamp', key: 'timestamp', width: 180, render: (value) => (value ? new Date(value).toLocaleString() : '-') },
              { title: '级别', dataIndex: 'level', key: 'level', width: 100, render: (value) => <Tag>{value || 'INFO'}</Tag> },
              { title: 'Trace ID', dataIndex: 'trace_id', key: 'trace_id', width: 220, render: (value) => value || '-' },
              { title: '分组', dataIndex: 'group', key: 'group', width: 140, render: (value) => value || '-' },
              { title: '状态码', dataIndex: 'status', key: 'status', width: 100, render: (value) => value ?? '-' },
              { title: '耗时(ms)', dataIndex: 'duration_ms', key: 'duration_ms', width: 120, render: (value) => value ?? '-' },
              { title: '消息', dataIndex: 'message', key: 'message', ellipsis: true }
            ]}
          />
        </Card>
      )
    }
  ]

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">系统面板</h2>
        <Button icon={<ReloadOutlined />} onClick={loadAll}>
          刷新
        </Button>
      </div>

      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />

      <Modal
        title={editTarget ? `编辑 ${editTarget.label}` : '编辑配置'}
        open={!!editTarget}
        onOk={async () => {
          const values = await configForm.validateFields()
          await sysConfigApi.update({ key: editTarget.key, value: values.value })
          message.success('配置已更新')
          setEditTarget(null)
          configForm.resetFields()
          loadAll()
        }}
        onCancel={() => {
          setEditTarget(null)
          configForm.resetFields()
        }}
      >
        <Form form={configForm} layout="vertical">
          <Form.Item
            name="value"
            label="配置值"
            rules={[{ required: true, message: '请输入配置值' }]}
          >
            <Input.TextArea rows={5} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default SystemPanel
