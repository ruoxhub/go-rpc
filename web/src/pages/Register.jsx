import { useState } from 'react'
import { Form, Input, Button, Card, message } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'

function Register() {
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()
  const navigate = useNavigate()

  const handleRegister = async (values) => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.append('userName', values.userName)
      params.append('password', values.password)

      const response = await axios.post('/sekiro-api/user-info/register', params, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded'
        }
      })

      if (response.data.status === 0) {
        message.success('注册成功，请登录')
        // 跳转到登录页
        navigate('/login')
      } else {
        message.error(response.data.message || '注册失败')
      }
    } catch (error) {
      console.error('Register error:', error)
      message.error(error.response?.data?.message || '注册失败，请检查网络连接')
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
        className="register-card"
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
          <h1 style={{ fontSize: 24, fontWeight: 600, margin: 0 }}>Sekiro 管理系统</h1>
        </div>

        <Form
          form={form}
          name="register"
          onFinish={handleRegister}
          size="large"
          disabled={loading}
        >
          <Form.Item
            name="userName"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 3, message: '用户名至少 3 个字符' }
            ]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="用户名"
              autoComplete="off"
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, message: '密码至少 6 个字符' }
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
              autoComplete="off"
            />
          </Form.Item>

          <Form.Item
            name="confirmPassword"
            dependencies={['password']}
            rules={[
              { required: true, message: '请确认密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'))
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="确认密码"
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
              注册
            </Button>
          </Form.Item>

          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <span style={{ color: 'rgba(0, 0, 0, 0.45)' }}>已有账号？</span>
            <Button type="link" onClick={() => navigate('/login')} style={{ padding: 0 }}>
              立即登录
            </Button>
          </div>
        </Form>
      </Card>
    </div>
  )
}

export default Register
