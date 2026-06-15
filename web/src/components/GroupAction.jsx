import { useState, useEffect } from 'react'
import { Card, Table, Button, Popconfirm, message, Modal, Form, Input, Tag, Tooltip } from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import { groupApi } from '../utils/api'

function GroupAction({ groupName, onRefresh }) {
  const [actions, setActions] = useState([])
  const [loading, setLoading] = useState(false)
  const [addModalVisible, setAddModalVisible] = useState(false)
  const [addForm] = Form.useForm()

  // 加载 Action 列表
  const loadActions = async () => {
    setLoading(true)
    try {
      const result = await groupApi.getActions(groupName)
      setActions((result.data || []).map(normalizeAction))
    } catch (error) {
      message.error('加载 Action 列表失败：' + (error.message || '未知错误'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadActions()
  }, [groupName])

  const toggleAddModal = (open) => {
    setAddModalVisible(open)
    if (!open) addForm.resetFields()
  }

  const handleAddModalOk = async () => {
    try {
      const values = await addForm.validateFields()
      await groupApi.addAction({
        groupName: groupName,
        actionName: values.actionName
      })
      message.success('Action 添加成功')
      toggleAddModal(false)
      loadActions()
      onRefresh && onRefresh()
    } catch (error) {
      if (error.response?.status === 409) {
        message.error('Action 名称已存在')
      } else if (error.errors) {
        return
      } else {
        message.error('添加 Action 失败：' + (error.message || '未知错误'))
      }
    }
  }

  const handleDeleteAction = async (actionName) => {
    try {
      await groupApi.deleteAction({ groupName, actionName })
      message.success('Action 删除成功')
      loadActions()
      onRefresh && onRefresh()
    } catch (error) {
      message.error('删除 Action 失败：' + (error.message || '未知错误'))
    }
  }

  const normalizeAction = (action) => ({
    ...action,
    actionName: action.actionName || action.action_name || '',
    groupName: action.groupName || action.group_name || groupName,
    actionParams: action.actionParams || action.action_params || '',
    createDate: action.createDate || action.create_date || ''
  })

  const parseActionParams = (value) => {
    if (!value) return []
    try {
      const params = JSON.parse(value)
      return Array.isArray(params) ? params : []
    } catch (error) {
      return []
    }
  }

  const renderActionParams = (value) => {
    const params = parseActionParams(value)
    if (params.length === 0) return '-'

    const summary = params.map((param) => {
      const required = param.required ? '必填' : '可选'
      const defaultText = param.default !== undefined && param.default !== null ? `，默认 ${param.default}` : ''
      return `${param.name}: ${param.type || 'any'}，${required}${defaultText}${param.description ? `，${param.description}` : ''}`
    }).join('\n')

    return (
      <Tooltip title={<pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{summary}</pre>}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, maxWidth: 520 }}>
          {params.slice(0, 5).map((param) => (
            <Tag key={param.name} color={param.required ? 'red' : 'blue'} style={{ marginInlineEnd: 0 }}>
              {param.name}
            </Tag>
          ))}
          {params.length > 5 && <Tag style={{ marginInlineEnd: 0 }}>+{params.length - 5}</Tag>}
        </div>
      </Tooltip>
    )
  }

  const renderCreateDate = (date) => {
    if (!date) return '-'
    const parsed = new Date(date)
    if (Number.isNaN(parsed.getTime())) return date
    return parsed.toLocaleString('zh-CN')
  }

  const getRowKey = (record) => {
    if (record.id) return record.id
    return `${record.groupName || groupName}:${record.actionName}`
  }

  const columns = [
    {
      title: 'Action 名称',
      dataIndex: 'actionName',
      key: 'actionName',
      width: 220
    },
    {
      title: '分组',
      dataIndex: 'groupName',
      key: 'groupName',
      width: 180
    },
    {
      title: '参数',
      dataIndex: 'actionParams',
      key: 'actionParams',
      render: renderActionParams
    },
    {
      title: '创建时间',
      dataIndex: 'createDate',
      key: 'createDate',
      width: 220,
      render: renderCreateDate
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_, record) => (
        <Popconfirm
          title="确定删除该 Action 吗？"
          onConfirm={() => handleDeleteAction(record.actionName)}
          okText="确定"
          cancelText="取消"
        >
          <Button size="small" danger icon={<DeleteOutlined />}>
            删除
          </Button>
        </Popconfirm>
      )
    }
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => toggleAddModal(true)}>
          添加 Action
        </Button>
      </div>

      <Card title={`Action 管理：${groupName}`}>
        <Table
          columns={columns}
          dataSource={actions}
          rowKey={getRowKey}
          loading={loading}
          size="middle"
          scroll={{ x: 1000 }}
          pagination={{
            pageSize: 10,
            total: actions.length,
            showSizeChanger: false,
            showTotal: (total) => `共 ${total} 条`
          }}
          locale={{
            emptyText: actions.length === 0 ? '暂无 Action，点击右上角添加' : '暂无数据'
          }}
        />
      </Card>

      <Modal
        title="添加 Action"
        open={addModalVisible}
        onOk={handleAddModalOk}
        onCancel={() => toggleAddModal(false)}
        okText="确定"
        cancelText="取消"
      >
        <Form form={addForm} layout="vertical">
          <Form.Item
            name="actionName"
            label="Action 名称"
            rules={[{ required: true, message: '请输入 Action 名称' }]}
          >
            <Input placeholder="请输入 Action 名称" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default GroupAction
