import { useState, useEffect } from 'react'
import { Card, Empty, Table, Space, Button, Popconfirm, message, Modal, Form, Input } from 'antd'
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
      setActions(result.data || [])
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

  const columns = [
    {
      title: 'Action 名称',
      dataIndex: 'actionName',
      key: 'actionName'
    },
    {
      title: '分组',
      dataIndex: 'groupName',
      key: 'groupName',
      render: () => groupName
    },
    {
      title: '创建时间',
      dataIndex: 'createDate',
      key: 'createDate',
      render: (date) => date ? new Date(date).toLocaleString('zh-CN') : '-'
    },
    {
      title: '操作',
      key: 'action',
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
          rowKey="id"
          loading={loading}
          pagination={{
            current: 1,
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
