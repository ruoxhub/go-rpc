import { useState } from 'react'
import { Tabs, Table, Descriptions, Collapse } from 'antd'

const { TabPane } = Collapse

// 模拟配置数据
const mockConfigs = [
  { key: 'sekiro.user.allowRegister', label: '是否允许注册用户', value: 'true' },
  { key: 'sekiro.outIpTestUrl', label: '出口 ip 探测 URL', value: 'http://example.com' },
  { key: 'sekiro.systemNotice', label: '系统通告信息', value: '' },
  { key: 'sekiro.docNotice', label: '文档首页通告信息', value: '' },
  { key: 'sekiro.allowAnonymousAccess', label: '是否允许匿名访问', value: 'true' },
  { key: 'sekiro.anonymousAccessRateLimit', label: '匿名访问 qps 限制', value: '10' },
  { key: 'sekiro.defaultRegisterQuotaUser', label: '注册用户默认 qps 限制', value: '10' },
  { key: 'sekiro.defaultRegisterQuotaGroup', label: '注册 group 默认 qps 限制', value: '100' },
  { key: 'sekiro.useCustomSSLCertificate', label: '使用自定义 ssl 证书', value: 'false' },
  { key: 'sekiro.autoGenSSLCertificateHostList', label: '为配置的 host 自动生成 ssl 证书', value: '' },
  { key: 'sekiro.open443Website', label: '开启 443 服务端口', value: 'false' },
  { key: 'sekiro.defendIdleInvoke', label: '空转调用保护', value: 'true' }
]

function SystemPanel() {
  const [activeKey, setActiveKey] = useState('config')

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">系统面板</h2>
      </div>

      <Tabs activeKey={activeKey} onChange={setActiveKey}>
        <TabPane tab="系统设置" key="config">
          <Table
            columns={[
              {
                title: '配置项',
                dataIndex: 'label',
                key: 'label',
                width: 300
              },
              {
                title: '配置值',
                dataIndex: 'value',
                key: 'value',
                render: (value) => value || '-'
              }
            ]}
            dataSource={mockConfigs}
            rowKey="key"
            pagination={false}
          />
        </TabPane>
        <TabPane tab="服务器节点" key="nodes">
          {/* TODO: 服务器节点列表 */}
        </TabPane>
        <TabPane tab="用户操作日志" key="logs">
          {/* TODO: 用户操作日志列表 */}
        </TabPane>
        <TabPane tab="构建信息" key="build">
          {/* TODO: 构建信息 */}
        </TabPane>
      </Tabs>
    </div>
  )
}

export default SystemPanel
