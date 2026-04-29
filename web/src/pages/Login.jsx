import { useState, useRef } from 'react'
import { Form, Input, Button, Card, message } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'

function Login() {
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()
  const navigate = useNavigate()

  const handleLogin = async (values) => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.append('userName', values.userName)
      params.append('password', values.password)

      const response = await axios.post('/rpc-api/user-info/login', params, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded'
        }
      })

      if (response.data.status === 0 && response.data.data) {
        // 保存 token 到 localStorage
        localStorage.setItem('api_token', response.data.data.apiToken)
        localStorage.setItem('login_token', response.data.data.loginToken)
        message.success('登录成功')
        // 跳转到首页
        window.location.href = '/dashboard'
      } else {
        message.error(response.data.message || '登录失败')
      }
    } catch (error) {
      console.error('Login error:', error)
      message.error(error.response?.data?.message || '登录失败，请检查网络连接')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
    }}>
      <Card
        className="login-card"
        style={{
          width: 400,
          boxShadow: '0 20px 60px rgba(0, 0, 0, 0.3)'
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 30 }}>
          <svg
            viewBox="0 0 32 32"
            fill="none"
            style={{ width: 64, height: 64, marginBottom: 16 }}
          >
            <circle
              cx="16"
              cy="16"
              r="14"
              stroke="#667eea"
              strokeWidth="2"
              fill="none"
            />
            <path
              d="M10 16L14 20L22 12"
              stroke="#667eea"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <h1 style={{ fontSize: 24, fontWeight: 600, margin: 0 }}>Rpc 管理系统</h1>
        </div>

        <Form
          form={form}
          name="login"
          onFinish={handleLogin}
          size="large"
          disabled={loading}
        >
          <Form.Item
            name="userName"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="用户名"
              autoComplete="off"
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
              autoComplete="off"
            />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              style={{ width: '100%', height: 44 }}
              size="large"
            >
              登录
            </Button>
          </Form.Item>

          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <span style={{ color: 'rgba(0, 0, 0, 0.45)' }}>没有账号？</span>
            <Button type="link" onClick={() => navigate('/register')} style={{ padding: 0 }}>
              立即注册
            </Button>
          </div>
        </Form>
      </Card>
    </div>
  )
}

export default Login
