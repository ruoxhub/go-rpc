import { useState } from 'react'
import { Card, Input, Button, Space, message, Divider } from 'antd'
import { CopyOutlined, ReloadOutlined } from '@ant-design/icons'
import { copyToClipboard } from '../utils'

function Dashboard() {
  const [apiToken, setApiToken] = useState('4d36cb9a-5a0d-4c4f-9c68-94c71f102207')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const handleCopyToken = async () => {
    try {
      await copyToClipboard(apiToken)
      message.success('已添加到剪贴板')
    } catch (err) {
      message.error('复制失败')
    }
  }

  const handleRefreshToken = () => {
    // TODO: 调用 API 刷新 token
    message.success('Token 已刷新')
  }

  const handleChangePassword = () => {
    if (!newPassword || !confirmPassword) {
      message.error('请输入密码')
      return
    }
    if (newPassword !== confirmPassword) {
      message.error('两次输入的密码不一致')
      return
    }
    // TODO: 调用 API 修改密码
    message.success('密码修改成功')
    setNewPassword('')
    setConfirmPassword('')
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>ruoxing</h2>
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
