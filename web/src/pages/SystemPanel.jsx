import { useEffect, useState } from 'react'
import { Button, Card, Input, InputNumber, Select, Switch, Table, Tabs, Tag, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { sysConfigApi } from '../utils/api'

// 配置项定义
const CONFIG_DEFINITIONS = [
  {
    key: 'sekiro.user.allowRegister',
    label: '是否允许注册用户',
    type: 'boolean',
    description: '设置不允许注册新用户，则可以避免用户空白注册，规避系统安全机制不完善，让敏感数据通过注册泄漏'
  },
  {
    key: 'sekiro.outIpTestUrl',
    label: '出口 ip 探测 URL',
    type: 'string',
    placeholder: '出口 ip 探测 URL',
    description: '计算当前服务器节点的出口 IP，用于多节点部署在公网时多节点事件通讯'
  },
  {
    key: 'sekiro.systemNotice',
    label: '系统通告信息',
    type: 'string',
    placeholder: '系统通告信息',
    description: '在框架前端系统，将会在用户 avatar 推送消息'
  },
  {
    key: 'sekiro.docNotice',
    label: '文档首页通告信息',
    type: 'string',
    placeholder: '文档首页通告信息',
    description: '在框架文档系统中，将会推送一段消息展示在文档中（此配置是 html 片段，故支持任意）'
  },
  {
    key: 'sekiro.allowAnonymousAccess',
    label: '是否允许匿名访问',
    type: 'boolean',
    description: '是否允许匿名访问'
  },
  {
    key: 'sekiro.anonymousAccessRateLimit',
    label: '匿名访问 qps 限制',
    type: 'number',
    description: '匿名访问 qps 限制'
  },
  {
    key: 'sekiro.defaultRegisterQuotaUser',
    label: '注册用户默认 qps 限制',
    type: 'number',
    description: '注册用户默认 qps 限制'
  },
  {
    key: 'sekiro.defaultRegisterQuotaGroup',
    label: '注册 group 默认 qps 限制',
    type: 'number',
    description: '注册 group 默认 qps 限制'
  },
  {
    key: 'sekiro.useCustomSSLCertificate',
    label: '使用自定义 ssl 证书',
    type: 'boolean',
    description: '使用自定义 ssl 证书'
  },
  {
    key: 'sekiro.autoGenSSLCertificateHostList',
    label: '为配置的 host 自动生成 ssl 证书',
    type: 'string',
    placeholder: '为配置的 host 自动生成 ssl 证书',
    description: '为配置的 host 自动生成 ssl 证书'
  },
  {
    key: 'sekiro.open443Website',
    label: '开启 443 服务端口',
    type: 'boolean',
    description: '开启 443 服务端口'
  },
  {
    key: 'sekiro.defendIdleInvoke',
    label: '空转调用保护',
    type: 'boolean',
    description: 'https://github.com/yint-tech/sekiro-open/blob/master/src/main/java/cn/iinti/sekiro3/open/core/client/NettyRpcGroup.java#L178'
  },
  {
    key: 'sekiro.allowedIPs',
    label: '全局 IP 白名单',
    type: 'iplist',
    description: '允许访问的 IP 或 CIDR 列表，逗号分隔。为空时不限制，loopback 始终放行'
  }
]

function SystemPanel() {
  const [configs, setConfigs] = useState([])
  const [nodes, setNodes] = useState([])
  const [sysLogs, setSysLogs] = useState([])
  const [appLogs, setAppLogs] = useState([])
  const [activeTab, setActiveTab] = useState('config')
  const [loading, setLoading] = useState(false)
  const [configValues, setConfigValues] = useState({})

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

      // 将配置值转换为表单值
      const values = {}
      ;(configResult.data || []).forEach(cfg => {
        values[cfg.key] = cfg.value
      })
      setConfigValues(values)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [])

  const parseValue = (key, value) => {
    const def = CONFIG_DEFINITIONS.find(d => d.key === key)
    if (!def) return value

    if (def.type === 'boolean') {
      return value === 'true' || value === '1' || value === true
    }
    if (def.type === 'number') {
      const num = parseFloat(value)
      return isNaN(num) ? 0 : num
    }
    return value || ''
  }

  // 保存配置
  const saveConfig = async (key, value) => {
    try {
      // 转换值为字符串
      let strValue
      if (typeof value === 'boolean') {
        strValue = value ? 'true' : 'false'
      } else if (typeof value === 'number') {
        strValue = String(value)
      } else {
        strValue = value || ''
      }

      await sysConfigApi.update({ key, value: strValue })
      message.success(`${CONFIG_DEFINITIONS.find(d => d.key === key)?.label || '配置'}已保存`)
      loadAll()
    } catch (error) {
      message.error('保存失败')
    }
  }

  const tabItems = [
    {
      key: 'config',
      label: '系统设置',
      children: (
        <Card loading={loading}>
          <Table
            rowKey="key"
            dataSource={CONFIG_DEFINITIONS.map(def => ({
              ...def,
              value: configs.find(c => c.key === def.key)?.value || ''
            }))}
            pagination={false}
            columns={[
              {
                title: '配置项',
                dataIndex: 'label',
                key: 'label',
                width: 280,
                render: (_, record) => (
                  <div>
                    <div>{record.label}</div>
                    <div style={{ color: '#999', fontSize: 12 }}>{record.description}</div>
                  </div>
                )
              },
              {
                title: '配置键',
                dataIndex: 'key',
                key: 'key',
                width: 320,
                render: (text) => <code style={{ backgroundColor: '#f5f5f5', padding: '2px 6px', borderRadius: 4 }}>{text}</code>
              },
              {
                title: '配置值',
                dataIndex: 'value',
                key: 'value',
                render: (_, record) => {
                  const parsedValue = parseValue(record.key, record.value)
                  if (record.type === 'boolean') {
                    return (
                      <Switch
                        checked={parsedValue}
                        onChange={(checked) => saveConfig(record.key, checked)}
                        checkedChildren="开"
                        unCheckedChildren="关"
                      />
                    )
                  }
                  if (record.type === 'number') {
                    return (
                      <InputNumber
                        value={parsedValue}
                        onChange={(val) => saveConfig(record.key, val)}
                        min={0}
                        step={1}
                        style={{ width: 150 }}
                      />
                    )
                  }
                  if (record.type === 'iplist') {
                    const tags = record.value
                      ? record.value.split(',').map(s => s.trim()).filter(Boolean)
                      : []
                    return (
                      <Select
                        mode="tags"
                        value={tags}
                        onChange={(vals) => setConfigValues(prev => ({ ...prev, [record.key]: vals.join(',') }))}
                        tokenSeparators={[',', ' ', '\n']}
                        placeholder="输入 IP 或 CIDR 后回车，如 192.168.1.0/24"
                        style={{ minWidth: 300 }}
                      />
                    )
                  }
                  return (
                    <Input
                      value={record.value}
                      onChange={(e) => setConfigValues(prev => ({ ...prev, [record.key]: e.target.value }))}
                      placeholder={record.placeholder}
                      style={{ width: 300 }}
                    />
                  )
                }
              },
              {
                title: '操作',
                key: 'action',
                width: 120,
                render: (_, record) => {
                  if (record.type === 'boolean') {
                    return null // 布尔类型不需要操作按钮
                  }
                  if (record.type === 'number') {
                    return null // 数字类型实时保存，不需要操作按钮
                  }
                  return (
                    <Button
                      type="primary"
                      size="small"
                      onClick={() => saveConfig(record.key, configValues[record.key] !== undefined ? configValues[record.key] : record.value)}
                    >
                      保存
                    </Button>
                  )
                }
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
    </div>
  )
}

export default SystemPanel
