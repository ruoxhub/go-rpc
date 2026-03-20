import { useState, useEffect } from 'react'
import { Tabs, Table, Descriptions, Input, Space, Button, message, Form, InputNumber, Modal } from 'antd'
import { SearchOutlined, EditOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import { useParams } from 'react-router-dom'
import GroupMonitor from '../components/GroupMonitor'
import GroupAction from '../components/GroupAction'
import GroupDeviceList from '../components/GroupDeviceList'
import { groupApi } from '../utils/api'

const { TabPane } = Tabs

function GroupDetail() {
  const { groupName } = useParams()
  const [activeTab, setActiveTab] = useState('basic')
  const [groupInfo, setGroupInfo] = useState(null)
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [qpsForm] = Form.useForm()

  // 加载分组详情
  const loadGroupDetail = async () => {
    setLoading(true)
    try {
      const result = await groupApi.getDetail(groupName)
      setGroupInfo(result.data)
    } catch (error) {
      message.error('加载分组详情失败：' + (error.message || '未知错误'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadGroupDetail()
  }, [groupName])

  const handleEditQps = () => {
    qpsForm.setFieldsValue({
      quotaQpsGroup: groupInfo.quotaQpsGroup,
      quotaQpsPerDevice: groupInfo.quotaQpsPerDevice
    })
    setEditing(true)
  }

  const handleSaveQps = async (values) => {
    try {
      await groupApi.updateQps({
        groupName: groupName,
        quotaQpsGroup: values.quotaQpsGroup,
        quotaQpsPerDevice: values.quotaQpsPerDevice
      })
      message.success('QPS 配置已保存')
      setEditing(false)
      loadGroupDetail()
    } catch (error) {
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

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab="基础信息" key="basic">
          {groupInfo && (
            <Descriptions column={3} bordered>
              <Descriptions.Item label="分组名称">{groupInfo.groupName}</Descriptions.Item>
              <Descriptions.Item label="所属用户">{groupInfo.userName}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{groupInfo.createTime}</Descriptions.Item>
              <Descriptions.Item label="在线客户端数量">
                <Space>
                  <span style={{ color: '#52c41a' }}>{groupInfo.availableClients}</span>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="禁用客户端数量">
                <span style={{ color: '#ff4d4f' }}>{groupInfo.disabledClients}</span>
              </Descriptions.Item>
              <Descriptions.Item label="QPS 限制">
                {editing ? (
                  <Form form={qpsForm} onFinish={handleSaveQps} layout="inline">
                    <Space>
                      <Form.Item name="quotaQpsGroup" label="分组 QPS">
                        <InputNumber min={1} />
                      </Form.Item>
                      <Form.Item name="quotaQpsPerDevice" label="设备 QPS">
                        <InputNumber min={-1} />
                      </Form.Item>
                      <Button type="primary" htmlType="submit">保存</Button>
                      <Button onClick={handleCancelEdit}>取消</Button>
                    </Space>
                  </Form>
                ) : (
                  <Space>
                    {groupInfo.quotaQpsGroup}
                    <Button type="primary" size="small" icon={<EditOutlined />} onClick={handleEditQps}>
                      编辑
                    </Button>
                  </Space>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="设备 QPS 限制">
                {editing ? (
                  <Form form={qpsForm} onFinish={handleSaveQps} layout="inline">
                    <Space>
                      <Form.Item name="quotaQpsGroup" label="分组 QPS">
                        <InputNumber min={1} />
                      </Form.Item>
                      <Form.Item name="quotaQpsPerDevice" label="设备 QPS">
                        <InputNumber min={-1} />
                      </Form.Item>
                      <Button type="primary" htmlType="submit">保存</Button>
                      <Button onClick={handleCancelEdit}>取消</Button>
                    </Space>
                  </Form>
                ) : (
                  <Space>
                    {groupInfo.quotaQpsPerDevice === -1 ? '不限制' : groupInfo.quotaQpsPerDevice}
                    <Button type="primary" size="small" icon={<EditOutlined />} onClick={handleEditQps}>
                      编辑
                    </Button>
                  </Space>
                )}
              </Descriptions.Item>
            </Descriptions>
          )}
        </TabPane>
        <TabPane tab="基础监控" key="monitor">
          <GroupMonitor groupName={groupName} />
        </TabPane>
        <TabPane tab="ACTION" key="action">
          <GroupAction groupName={groupName} onRefresh={loadGroupDetail} />
        </TabPane>
        <TabPane tab="设备列表" key="devices">
          <GroupDeviceList groupName={groupName} onRefresh={loadGroupDetail} />
        </TabPane>
      </Tabs>
    </div>
  )
}

export default GroupDetail
