import { useState, useEffect } from 'react'
import { Tabs, Descriptions, Space, Button, message, Form, InputNumber } from 'antd'
import { EditOutlined } from '@ant-design/icons'
import { useParams } from 'react-router-dom'
import GroupMonitor from '../components/GroupMonitor'
import GroupAction from '../components/GroupAction'
import GroupDeviceList from '../components/GroupDeviceList'
import { groupApi } from '../utils/api'

function GroupDetail() {
  const { groupName } = useParams()
  const [activeTab, setActiveTab] = useState('basic')
  const [groupInfo, setGroupInfo] = useState(null)
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [qpsForm] = Form.useForm()

  // 加载分组详情（支持 silent 静默轮询）
  const loadGroupDetail = async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const result = await groupApi.getDetail(groupName)
      setGroupInfo(result.data)
    } catch (error) {
      if (!silent) {
        message.error('加载分组详情失败：' + (error.message || '未知错误'))
      }
    } finally {
      if (!silent) setLoading(false)
    }
  }

  useEffect(() => {
    loadGroupDetail()
    const timer = setInterval(() => {
      // 若当前正在编辑 QPS 表单，暂缓静默覆盖
      if (!editing) {
        loadGroupDetail(true)
      }
    }, 5000)
    return () => clearInterval(timer)
  }, [groupName, editing])

  const handleEditQps = () => {
    setEditing(true)
    setTimeout(() => {
      qpsForm.setFieldsValue({
        quotaQpsGroup: groupInfo.quotaQpsGroup,
        quotaQpsPerDevice: groupInfo.quotaQpsPerDevice
      })
    }, 0)
  }

  const handleSaveQps = async () => {
    try {
      const values = await qpsForm.validateFields()
      await groupApi.updateQps({
        groupName: groupName,
        quotaQpsGroup: values.quotaQpsGroup,
        quotaQpsPerDevice: values.quotaQpsPerDevice
      })
      message.success('分组配置已保存')
      setEditing(false)
      loadGroupDetail()
    } catch (error) {
      if (error.errors) return
      message.error('保存失败：' + (error.message || '未知错误'))
    }
  }

  const handleCancelEdit = () => {
    setEditing(false)
    qpsForm.resetFields()
  }

  if (loading && !groupInfo) {
    return <div>加载中...</div>
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>{groupName}</h2>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'basic',
            label: '基础信息',
            children: groupInfo && (
              <>
                <Form form={qpsForm} component={editing ? 'form' : false}>
                <Descriptions column={3} bordered>
                <Descriptions.Item label="分组名称">{groupInfo.groupName}</Descriptions.Item>
                <Descriptions.Item label="所属用户">{groupInfo.userName}</Descriptions.Item>
                <Descriptions.Item label="创建时间">{groupInfo.createTime}</Descriptions.Item>
                <Descriptions.Item label="在线客户端数量">
                  <span style={{ color: '#52c41a' }}>{groupInfo.availableClients}</span>
                </Descriptions.Item>
                <Descriptions.Item label="QPS 限制">
                  <Space>
                    {editing
                      ? <Form.Item name="quotaQpsGroup" style={{ marginBottom: 0 }}><InputNumber min={1} /></Form.Item>
                      : groupInfo.quotaQpsGroup}
                    {!editing && (
                      <Button type="primary" size="small" icon={<EditOutlined />} onClick={handleEditQps}>
                        编辑
                      </Button>
                    )}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="设备 QPS 限制">
                  <Space>
                    {editing
                      ? <Form.Item name="quotaQpsPerDevice" style={{ marginBottom: 0 }}><InputNumber min={-1} /></Form.Item>
                      : (groupInfo.quotaQpsPerDevice === -1 ? '不限制' : groupInfo.quotaQpsPerDevice)}
                    {!editing && (
                      <Button type="primary" size="small" icon={<EditOutlined />} onClick={handleEditQps}>
                        编辑
                      </Button>
                    )}
                  </Space>
                </Descriptions.Item>
                {editing && (
                  <Descriptions.Item label="" span={3}>
                    <Space>
                      <Button type="primary" onClick={handleSaveQps}>保存</Button>
                      <Button onClick={handleCancelEdit}>取消</Button>
                    </Space>
                  </Descriptions.Item>
                )}
              </Descriptions>
                </Form>
              </>
            )
          },
          {
            key: 'monitor',
            label: '基础监控',
            children: <GroupMonitor groupName={groupName} />
          },
          {
            key: 'action',
            label: 'ACTION',
            children: <GroupAction groupName={groupName} onRefresh={loadGroupDetail} />
          },
          {
            key: 'devices',
            label: '设备列表',
            children: <GroupDeviceList groupName={groupName} onRefresh={loadGroupDetail} />
          }
        ]}
      />
    </div>
  )
}

export default GroupDetail
