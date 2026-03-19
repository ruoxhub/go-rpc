import { useState } from 'react'
import { Tabs, Table, Descriptions, Input, Space, Button, message, Form, InputNumber } from 'antd'
import { SearchOutlined, EditOutlined } from '@ant-design/icons'
import { useParams } from 'react-router-dom'
import GroupMonitor from '../components/GroupMonitor'
import GroupAction from '../components/GroupAction'
import GroupDeviceList from '../components/GroupDeviceList'

const { TabPane } = Tabs

// 模拟数据
const mockGroupInfo = {
  groupName: 'github',
  userName: 'ruoxing',
  createTime: '2026-03-19T19:44:01',
  availableClients: 1,
  disabledClients: 0,
  quotaQpsGroup: 10,
  quotaQpsPerDevice: 100
}

function GroupDetail() {
  const { groupName } = useParams()
  const [activeTab, setActiveTab] = useState('basic')
  const [groupInfo] = useState(mockGroupInfo)
  const [editing, setEditing] = useState(false)

  const handleEditQps = () => {
    setEditing(true)
  }

  const handleSaveQps = (values) => {
    // TODO: 调用 API 保存 QPS 配置
    message.success('QPS 配置已保存')
    setEditing(false)
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>{groupName}</h2>
      </div>

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab="基础信息" key="basic">
          <Descriptions column={3} bordered>
            <Descriptions.Item label="groupName">{groupInfo.groupName}</Descriptions.Item>
            <Descriptions.Item label="分组名">{groupInfo.userName}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{groupInfo.createTime}</Descriptions.Item>
            <Descriptions.Item label="在线客户端数量">{groupInfo.availableClients}</Descriptions.Item>
            <Descriptions.Item label="禁用客户端数量">{groupInfo.disabledClients}</Descriptions.Item>
            <Descriptions.Item label="qps 限制">
              {editing ? (
                <Form onFinish={handleSaveQps}>
                  <Space>
                    <InputNumber
                      defaultValue={groupInfo.quotaQpsGroup}
                      name="quotaQpsGroup"
                    />
                    <Button type="primary" htmlType="submit">保存</Button>
                    <Button onClick={() => setEditing(false)}>取消</Button>
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
                <Form onFinish={handleSaveQps}>
                  <Space>
                    <InputNumber
                      defaultValue={groupInfo.quotaQpsPerDevice}
                      name="quotaQpsPerDevice"
                    />
                    <Button type="primary" htmlType="submit">保存</Button>
                    <Button onClick={() => setEditing(false)}>取消</Button>
                  </Space>
                </Form>
              ) : (
                <Space>
                  {groupInfo.quotaQpsPerDevice}
                  <Button type="primary" size="small" icon={<EditOutlined />} onClick={handleEditQps}>
                    编辑
                  </Button>
                </Space>
              )}
            </Descriptions.Item>
          </Descriptions>
        </TabPane>
        <TabPane tab="基础监控" key="monitor">
          <GroupMonitor groupName={groupName} />
        </TabPane>
        <TabPane tab="ACTION" key="action">
          <GroupAction groupName={groupName} />
        </TabPane>
        <TabPane tab="设备列表" key="devices">
          <GroupDeviceList groupName={groupName} />
        </TabPane>
      </Tabs>
    </div>
  )
}

export default GroupDetail
