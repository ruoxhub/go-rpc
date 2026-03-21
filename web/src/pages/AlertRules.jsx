import { useState, useEffect } from 'react'
import { Card, Table, Form, Input, Select, Button, Space, Modal, message, Tag, Popconfirm, Divider } from 'antd'
import { SearchOutlined, PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import axios from 'axios'

const { Option } = Select
const { TextArea } = Input

// 获取 API 基础路径
const getApiBase = () => {
  const host = window.location.hostname
  const port = window.location.port
  return `http://${host}:${port}/api`
}

function AlertRules() {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [rules, setRules] = useState([])
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  })
  const [modalVisible, setModalVisible] = useState(false)
  const [editingRule, setEditingRule] = useState(null)
  const [selectedGroup, setSelectedGroup] = useState(null)

  // 告警规则表单字段
  const formFields = {
    name: { label: '规则名称', required: true },
    description: { label: '描述' },
    group: { label: '分组' },
    api: { label: 'API' },
    metricName: { label: '指标名称', required: true },
    operator: { label: '操作符', required: true },
    threshold: { label: '阈值', required: true, type: 'number' },
    window: { label: '时间窗口 (分钟)', required: true, type: 'number' },
    webhookUrl: { label: 'Webhook URL' },
    email: { label: '通知邮箱' },
    enabled: { label: '启用', type: 'boolean' },
  }

  // 获取告警规则列表
  const fetchRules = async (params = {}) => {
    setLoading(true)
    try {
      const queryParams = {
        page: params.current || 1,
        pageSize: params.pageSize || 20,
        ...form.getFieldsValue(),
      }

      if (selectedGroup) {
        queryParams.group = selectedGroup
      }

      const response = await axios.get(`${getApiBase()}/alerts/rules`, { params: queryParams })

      if (response.data.code === 0) {
        setRules(response.data.data || [])
        setPagination({
          current: params.current || 1,
          pageSize: params.pageSize || 20,
          total: response.data.total || 0,
        })
      }
    } catch (error) {
      console.error('获取告警规则失败:', error)
      message.error('获取告警规则失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchRules()
  }, [])

  // 搜索
  const handleSearch = () => {
    fetchRules({ current: 1, pageSize: pagination.pageSize })
  }

  // 重置
  const handleReset = () => {
    form.resetFields()
    setSelectedGroup(null)
    fetchRules({ current: 1, pageSize: pagination.pageSize })
  }

  // 表格变化
  const handleTableChange = (newPagination) => {
    fetchRules({
      current: newPagination.current,
      pageSize: newPagination.pageSize,
    })
  }

  // 打开创建/编辑弹窗
  const openModal = (rule = null) => {
    setEditingRule(rule)
    if (rule) {
      form.setFieldsValue(rule)
    } else {
      form.resetFields()
    }
    setModalVisible(true)
  }

  // 保存规则
  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const url = editingRule
        ? `${getApiBase()}/alerts/rules/${editingRule.id}`
        : `${getApiBase()}/alerts/rules`

      const method = editingRule ? 'put' : 'post'

      const response = await axios({
        method,
        url,
        data: values,
      })

      if (response.data.code === 0) {
        message.success(editingRule ? '更新成功' : '创建成功')
        setModalVisible(false)
        fetchRules({ current: 1, pageSize: pagination.pageSize })
      }
    } catch (error) {
      if (error.response?.data?.message) {
        message.error(error.response.data.message)
      }
    }
  }

  // 删除规则
  const handleDelete = async (id) => {
    try {
      const response = await axios.delete(`${getApiBase()}/alerts/rules/${id}`)
      if (response.data.code === 0) {
        message.success('删除成功')
        fetchRules({ current: 1, pageSize: pagination.pageSize })
      }
    } catch (error) {
      message.error('删除失败')
    }
  }

  // 切换启用状态
  const toggleEnabled = async (record) => {
    try {
      const response = await axios.put(`${getApiBase()}/alerts/rules/${record.id}`, {
        id: record.id,
        enabled: !record.enabled,
      })
      if (response.data.code === 0) {
        message.success(record.enabled ? '已禁用' : '已启用')
        fetchRules()
      }
    } catch (error) {
      message.error('操作失败')
    }
  }

  // 表格列定义
  const columns = [
    {
      title: '规则名称',
      dataIndex: 'name',
      key: 'name',
      width: 180,
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
      title: '指标名称',
      dataIndex: 'metricName',
      key: 'metricName',
      width: 150,
      ellipsis: true,
    },
    {
      title: '条件',
      key: 'condition',
      width: 150,
      render: (_, record) => (
        <span>
          {record.operator} {record.threshold}
        </span>
      ),
    },
    {
      title: '窗口',
      dataIndex: 'window',
      key: 'window',
      width: 80,
      render: (text) => `${text}分钟`,
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled) => (
        <Tag color={enabled ? 'green' : 'red'}>
          {enabled ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 160,
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_, record) => (
        <Space>
          <a onClick={() => openModal(record)}>编辑</a>
          <a onClick={() => toggleEnabled(record)}>
            {record.enabled ? '禁用' : '启用'}
          </a>
          <Popconfirm
            title="确定删除此规则吗？"
            onConfirm={() => handleDelete(record.id)}
          >
            <a style={{ color: 'red' }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline">
          <Form.Item name="group" label="分组">
            <Input placeholder="输入分组名称" allowClear style={{ width: 150 }} />
          </Form.Item>

          <Form.Item name="metricName" label="指标名称">
            <Input placeholder="输入指标名称" allowClear style={{ width: 180 }} />
          </Form.Item>

          <Form.Item name="enabled" label="状态" initialValue={true}>
            <Select allowClear style={{ width: 120 }}>
              <Option value={true}>启用</Option>
              <Option value={false}>禁用</Option>
            </Select>
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
                查询
              </Button>
              <Button icon={<ReloadOutlined />} onClick={handleReset}>
                重置
              </Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal()}>
                新建规则
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      <Card>
        <Table
          columns={columns}
          dataSource={rules}
          loading={loading}
          pagination={pagination}
          onChange={handleTableChange}
          rowKey="id"
          scroll={{ x: 1400 }}
        />
      </Card>

      {/* 新建/编辑弹窗 */}
      <Modal
        title={editingRule ? '编辑告警规则' : '新建告警规则'}
        open={modalVisible}
        onOk={handleSave}
        onCancel={() => setModalVisible(false)}
        width={700}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label={formFields.name.label}
            rules={[{ required: formFields.name.required, message: `请输入${formFields.name.label}` }]}
          >
            <Input placeholder="输入规则名称" />
          </Form.Item>

          <Form.Item name="description" label={formFields.description.label}>
            <TextArea rows={2} placeholder="输入规则描述" />
          </Form.Item>

          <Form.Item name="group" label={formFields.group.label}>
            <Input placeholder="输入分组名称（留空表示全局规则）" />
          </Form.Item>

          <Form.Item name="api" label={formFields.api.label}>
            <Input placeholder="输入 API（留空表示所有 API）" />
          </Form.Item>

          <Form.Item
            name="metricName"
            label={formFields.metricName.label}
            rules={[{ required: formFields.metricName.required, message: `请输入${formFields.metricName.label}` }]}
          >
            <Select placeholder="选择指标名称">
              <Option value="invoke.total">invoke.total (调用次数)</Option>
              <Option value="invoke.latency">invoke.latency (调用延迟)</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="operator"
            label={formFields.operator.label}
            rules={[{ required: formFields.operator.required, message: `请选择${formFields.operator.label}` }]}
          >
            <Select placeholder="选择操作符">
              <Option value=">">&gt; (大于)</Option>
              <Option value="<">&lt; (小于)</Option>
              <Option value=">=">&gt;= (大于等于)</Option>
              <Option value="<=">&lt;= (小于等于)</Option>
              <Option value="==">== (等于)</Option>
              <Option value="!=">!= (不等于)</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="threshold"
            label={formFields.threshold.label}
            rules={[{ required: formFields.threshold.required, message: `请输入${formFields.threshold.label}` }]}
          >
            <Input type="number" placeholder="输入阈值" />
          </Form.Item>

          <Form.Item
            name="window"
            label={formFields.window.label}
            rules={[{ required: formFields.window.required, message: `请输入${formFields.window.label}` }]}
          >
            <Input type="number" placeholder="输入时间窗口（分钟）" />
          </Form.Item>

          <Form.Item name="webhookUrl" label={formFields.webhookUrl.label}>
            <Input placeholder="输入 Webhook URL" />
          </Form.Item>

          <Form.Item name="email" label={formFields.email.label}>
            <Input placeholder="输入通知邮箱" />
          </Form.Item>

          <Form.Item name="enabled" label={formFields.enabled.label} initialValue={true} valuePropName="checked">
            <Select>
              <Option value={true}>启用</Option>
              <Option value={false}>禁用</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default AlertRules
