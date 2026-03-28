import { useEffect, useState } from 'react'
import { Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tag, message } from 'antd'
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { alertApi } from '../utils/api'

function AlertRules() {
  const [searchForm] = Form.useForm()
  const [modalForm] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [rules, setRules] = useState([])
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const [modalOpen, setModalOpen] = useState(false)
  const [editingRule, setEditingRule] = useState(null)

  const loadRules = async (pageConfig = {}) => {
    setLoading(true)
    try {
      const fields = searchForm.getFieldsValue()
      const params = {
        page: pageConfig.current || pagination.current,
        pageSize: pageConfig.pageSize || pagination.pageSize,
        group: fields.group
      }
      if (fields.enabled !== undefined) {
        params.enabled = fields.enabled
      }

      const result = await alertApi.getRules(params)
      setRules(result.data || [])
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
    loadRules({ current: 1, pageSize: 20 })
  }, [])

  const openModal = (rule) => {
    setEditingRule(rule || null)
    modalForm.setFieldsValue(rule || { enabled: true, window: 5 })
    setModalOpen(true)
  }

  const handleSave = async () => {
    const values = await modalForm.validateFields()
    if (editingRule) {
      await alertApi.updateRule(editingRule.id, { id: editingRule.id, ...values })
      message.success('规则已更新')
    } else {
      await alertApi.createRule(values)
      message.success('规则已创建')
    }
    setModalOpen(false)
    setEditingRule(null)
    modalForm.resetFields()
    loadRules({ current: 1, pageSize: pagination.pageSize })
  }

  const columns = [
    { title: '规则名称', dataIndex: 'name', key: 'name', width: 180, ellipsis: true },
    { title: '分组', dataIndex: 'group', key: 'group', width: 140, render: (value) => value || '-' },
    { title: 'API', dataIndex: 'api', key: 'api', width: 180, render: (value) => value || '-' },
    { title: '指标', dataIndex: 'metricName', key: 'metricName', width: 160 },
    {
      title: '条件',
      key: 'condition',
      width: 120,
      render: (_, record) => `${record.operator} ${record.threshold}`
    },
    {
      title: '窗口',
      dataIndex: 'window',
      key: 'window',
      width: 100,
      render: (value) => `${value} 分钟`
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 100,
      render: (value) => <Tag color={value ? 'green' : 'red'}>{value ? '启用' : '禁用'}</Tag>
    },
    { title: '更新时间', dataIndex: 'updatedAt', key: 'updatedAt', width: 180 },
    {
      title: '操作',
      key: 'action',
      width: 220,
      render: (_, record) => (
        <Space>
          <a onClick={() => openModal(record)}>编辑</a>
          <a
            onClick={async () => {
              await alertApi.updateRule(record.id, { id: record.id, enabled: !record.enabled })
              message.success(record.enabled ? '规则已禁用' : '规则已启用')
              loadRules()
            }}
          >
            {record.enabled ? '禁用' : '启用'}
          </a>
          <Popconfirm
            title="确定删除该规则吗？"
            okText="删除"
            cancelText="取消"
            onConfirm={async () => {
              await alertApi.deleteRule(record.id)
              message.success('规则已删除')
              loadRules()
            }}
          >
            <a style={{ color: 'red' }}>删除</a>
          </Popconfirm>
        </Space>
      )
    }
  ]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>告警规则</h2>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Form form={searchForm} layout="inline">
          <Form.Item name="group" label="分组">
            <Input allowClear />
          </Form.Item>
          <Form.Item name="enabled" label="状态">
            <Select allowClear style={{ width: 120 }}>
              <Select.Option value={true}>启用</Select.Option>
              <Select.Option value={false}>禁用</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} onClick={() => loadRules({ current: 1 })}>
                查询
              </Button>
              <Button
                icon={<ReloadOutlined />}
                onClick={() => {
                  searchForm.resetFields()
                  loadRules({ current: 1, pageSize: pagination.pageSize })
                }}
              >
                重置
              </Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal(null)}>
                新建规则
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      <Card>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={rules}
          columns={columns}
          pagination={pagination}
          onChange={(pager) => loadRules({ current: pager.current, pageSize: pager.pageSize })}
          scroll={{ x: 1500 }}
        />
      </Card>

      <Modal
        title={editingRule ? '编辑告警规则' : '新建告警规则'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => {
          setModalOpen(false)
          setEditingRule(null)
          modalForm.resetFields()
        }}
      >
        <Form form={modalForm} layout="vertical" initialValues={{ enabled: true, window: 5 }}>
          <Form.Item name="name" label="规则名称" rules={[{ required: true, message: '请输入规则名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="group" label="分组">
            <Input />
          </Form.Item>
          <Form.Item name="api" label="API">
            <Input />
          </Form.Item>
          <Form.Item name="metricName" label="指标名称" rules={[{ required: true, message: '请选择指标' }]}>
            <Select>
              <Select.Option value="invoke.total">invoke.total</Select.Option>
              <Select.Option value="invoke.latency">invoke.latency</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="operator" label="操作符" rules={[{ required: true, message: '请选择操作符' }]}>
            <Select>
              <Select.Option value=">">&gt;</Select.Option>
              <Select.Option value="<">&lt;</Select.Option>
              <Select.Option value=">=">&gt;=</Select.Option>
              <Select.Option value="<=">&lt;=</Select.Option>
              <Select.Option value="==">==</Select.Option>
              <Select.Option value="!=">!=</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="threshold" label="阈值" rules={[{ required: true, message: '请输入阈值' }]}>
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="window" label="时间窗口（分钟）" rules={[{ required: true, message: '请输入时间窗口' }]}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="webhookUrl" label="Webhook URL">
            <Input />
          </Form.Item>
          <Form.Item name="email" label="通知邮箱">
            <Input />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default AlertRules
