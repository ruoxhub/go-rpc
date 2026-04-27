import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Spin } from 'antd'

function AuthGuard({ children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [checked, setChecked] = useState(false)
  const [authenticated, setAuthenticated] = useState(false)

  useEffect(() => {
    const apiToken = localStorage.getItem('api_token')
    const isAuth = !!apiToken
    setAuthenticated(isAuth)

    if (!isAuth && location.pathname !== '/login') {
      navigate('/login', { state: { from: location }, replace: true })
    }
    setChecked(true)
  }, [navigate, location])

  if (!checked) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!authenticated && location.pathname !== '/login') {
    return null
  }

  return children
}

export default AuthGuard
