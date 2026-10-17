import { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu } from 'antd'
import {
  HomeOutlined,
  TeamOutlined,
  LineChartOutlined,
  UserOutlined,
  SettingOutlined,
  ArrowLeftOutlined,
  ApartmentOutlined,
  BellOutlined,
  HistoryOutlined
} from '@ant-design/icons'
import { userApi } from '../utils/api'

const { Sider, Content } = Layout

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
    key: '/monitor',
    icon: <LineChartOutlined />,
    label: '监控指标'
  },
  {
    key: '/traces',
    icon: <ApartmentOutlined />,
    label: '调用追踪'
  },
  {
    key: '/alerts',
    icon: <BellOutlined />,
    label: '告警规则'
  },
  {
    key: '/alert-history',
    icon: <HistoryOutlined />,
    label: '告警历史'
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
  const [userName, setUserName] = useState('')

  // 获取当前用户信息
  useEffect(() => {
    const loadUser = async () => {
      try {
        const result = await userApi.getCurrentUser()
        if (result.data) {
          setUserName(result.data.userName)
        }
      } catch (error) {
        console.error('加载用户信息失败:', error)
      }
    }
    loadUser()
  }, [])

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
          <span className="sidebar-title">{userName || '加载中...'}</span>
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
      </Layout>
    </Layout>
  )
}

export default LayoutComponent
