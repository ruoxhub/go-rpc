import { useState, useEffect } from 'react'
import { Card, Input, Button, Space, message, Divider } from 'antd'
import { CopyOutlined, ReloadOutlined } from '@ant-design/icons'
import { copyToClipboard } from '../utils'
import { userApi } from '../utils/api'

function Dashboard() {
  const [apiToken, setApiToken] = useState('')
  const [userName, setUserName] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  // 加载当前用户信息
  useEffect(() => {
    loadCurrentUser()
  }, [])

  const loadCurrentUser = async () => {
    try {
      const result = await userApi.getCurrentUser()
      if (result.data) {
        setApiToken(result.data.apiToken)
        setUserName(result.data.userName)
      }
    } catch (error) {
      console.error('加载用户信息失败:', error)
      // 如果是 401 错误，清除 token 并重定向到登录页
      if (error.response?.status === 401 || error.response?.status === 403) {
        localStorage.removeItem('api_token')
        localStorage.removeItem('login_token')
        window.location.href = '/login'
      }
    }
  }

  const handleCopyToken = async () => {
    try {
      await copyToClipboard(apiToken)
      message.success('已添加到剪贴板')
    } catch (err) {
      message.error('复制失败')
    }
  }

  const handleRefreshToken = async () => {
    try {
      const result = await userApi.refreshToken()
      if (result.data?.apiToken) {
        setApiToken(result.data.apiToken)
        // 更新 localStorage 中的 token
        localStorage.setItem('api_token', result.data.apiToken)
        message.success('Token 已刷新')
      }
    } catch (error) {
      message.error('刷新 Token 失败：' + (error.message || '未知错误'))
    }
  }

  const handleChangePassword = async () => {
    if (!newPassword || !confirmPassword) {
      message.error('请输入密码')
      return
    }
    if (newPassword !== confirmPassword) {
      message.error('两次输入的密码不一致')
      return
    }
    try {
      await userApi.changePassword({ newPassword })
      message.success('密码修改成功')
      setNewPassword('')
      setConfirmPassword('')
    } catch (error) {
      message.error('修改密码失败：' + (error.message || '未知错误'))
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>{userName || '加载中...'}</h2>
      </div>

      <Card title="API TOKEN" style={{ marginBottom: 24 }}>
        <Space.Compact style={{ width: '100%' }}>
          <Input value={apiToken} readOnly style={{ flex: 1 }} />
          <Button icon={<CopyOutlined />} onClick={handleCopyToken} />
          <Button icon={<ReloadOutlined />} onClick={handleRefreshToken} />
        </Space.Compact>
      </Card>

      <Card title="修改密码">
        <Divider />
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          <Space style={{ width: '100%' }}>
            <Input.Password
              placeholder="新密码"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              style={{ width: 300 }}
            />
            <Input.Password
              placeholder="再次输入密码"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              style={{ width: 300 }}
            />
            <Button type="primary" onClick={handleChangePassword}>
              应用
            </Button>
          </Space>
        </Space>
      </Card>
    </div>
  )
}

export default Dashboard
