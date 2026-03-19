import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu } from 'antd'
import {
  HomeOutlined,
  TeamOutlined,
  DashboardOutlined,
  LineChartOutlined,
  UserOutlined,
  SettingOutlined,
  ArrowLeftOutlined
} from '@ant-design/icons'

const { Sider, Content, Footer } = Layout

const menuItems = [
  {
    key: '/dashboard',
    icon: <HomeOutlined />,
    label: '我的'
  },
  {
    key: '/groups',
    icon: <TeamOutlined />,
    label: '分组列表'
  },
  {
    key: '/anonymous-groups',
    icon: <DashboardOutlined />,
    label: '匿名分组'
  },
  {
    key: '/monitor',
    icon: <LineChartOutlined />,
    label: '监控指标'
  },
  {
    key: '/users',
    icon: <UserOutlined />,
    label: '账号列表'
  },
  {
    key: '/system',
    icon: <SettingOutlined />,
    label: '系统面板'
  }
]

function LayoutComponent() {
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)

  // 检查是否是分组详情页面
  const isGroupDetail = location.pathname.startsWith('/group/')

  return (
    <Layout className="main-layout">
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={(value) => setCollapsed(value)}
        theme="light"
        style={{
          borderRight: '1px solid #f0f0f0'
        }}
      >
        <div className="sidebar-header" style={{ background: '#1890ff' }}>
          <svg className="sidebar-logo" viewBox="0 0 32 32" fill="none">
            <circle cx="16" cy="16" r="14" stroke="white" strokeWidth="2" fill="none" />
            <path d="M10 16L14 20L22 12" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="sidebar-title">ruoxing</span>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{
            borderRight: 0,
            marginTop: 16
          }}
        />
      </Sider>
      <Layout>
        <Content style={{ margin: '24px 16px' }}>
          {isGroupDetail && (
            <div style={{ marginBottom: 16 }}>
              <a onClick={() => navigate('/groups')}>
                <ArrowLeftOutlined /> 返回
              </a>
            </div>
          )}
          <div className="page-container">
            <Outlet />
          </div>
        </Content>
        <Footer style={{ textAlign: 'center' }}>
          sekiro-系统框架 © 2023 因体信息公司 因体产品 | Majora | Sekiro | Malenia
        </Footer>
      </Layout>
    </Layout>
  )
}

export default LayoutComponent
