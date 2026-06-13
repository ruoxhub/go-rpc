import { useState, useEffect } from 'react'
import { Tabs, Descriptions, Input, Space, Button, message, Form, InputNumber, Tag } from 'antd'
import { EditOutlined } from '@ant-design/icons'
import { useParams } from 'react-router-dom'
import GroupMonitor from '../components/GroupMonitor'
import GroupAction from '../components/GroupAction'
import GroupDeviceList from '../components/GroupDeviceList'
import { groupApi } from '../utils/api'

const { TextArea } = Input

function formatAllowedIps(raw) {
  if (!raw) return []
  return raw.split(',').map((s) => s.trim()).filter(Boolean)
}

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
    setEditing(true)
    setTimeout(() => {
      qpsForm.setFieldsValue({
        quotaQpsGroup: groupInfo.quotaQpsGroup,
        quotaQpsPerDevice: groupInfo.quotaQpsPerDevice,
        allowedIps: groupInfo.allowedIps || ''
      })
    }, 0)
  }

  const handleSaveQps = async () => {
    try {
      const values = await qpsForm.validateFields()
      await groupApi.updateQps({
        groupName: groupName,
        quotaQpsGroup: values.quotaQpsGroup,
        quotaQpsPerDevice: values.quotaQpsPerDevice,
        allowedIps: (values.allowedIps || '').trim()
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

  const allowedIpList = formatAllowedIps(groupInfo?.allowedIps)

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
                <Descriptions.Item label="禁用客户端数量">
                  <span style={{ color: '#ff4d4f' }}>{groupInfo.disabledClients}</span>
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
                <Descriptions.Item label="IP 白名单" span={3}>
                  {editing ? (
                    <Form.Item
                      name="allowedIps"
                      style={{ marginBottom: 0 }}
                      extra="留空表示不启用白名单；支持精确 IP 或 CIDR，多项用逗号分隔，例如：10.0.0.0/8, 203.0.113.5"
                      rules={[
                        {
                          validator: (_, value) => {
                            const entries = (value || '').split(',').map((s) => s.trim()).filter(Boolean)
                            const ipRe = /^[\da-fA-F.:]+$/
                            const cidrRe = /^[\da-fA-F.:]+\/\d+$/
                            for (const e of entries) {
                              if (!ipRe.test(e) && !cidrRe.test(e)) {
                                return Promise.reject(new Error(`非法条目：${e}`))
                              }
                            }
                            return Promise.resolve()
                          }
                        }
                      ]}
                    >
                      <TextArea rows={2} placeholder="例如：10.0.0.0/8, 192.168.1.5" />
                    </Form.Item>
                  ) : allowedIpList.length === 0 ? (
                    <Space>
                      <Tag color="default">未启用（公开）</Tag>
                      <Button type="primary" size="small" icon={<EditOutlined />} onClick={handleEditQps}>
                        配置
                      </Button>
                    </Space>
                  ) : (
                    <Space wrap>
                      {allowedIpList.map((ip) => (
                        <Tag key={ip} color="blue">{ip}</Tag>
                      ))}
                      <Button type="primary" size="small" icon={<EditOutlined />} onClick={handleEditQps}>
                        编辑
                      </Button>
                    </Space>
                  )}
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
