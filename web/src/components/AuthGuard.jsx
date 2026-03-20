import { useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'

function AuthGuard({ children }) {
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const apiToken = localStorage.getItem('api_token')

    // 如果没有 token 且不在登录页，跳转到登录页
    if (!apiToken && location.pathname !== '/login') {
      navigate('/login', { state: { from: location } })
    }
  }, [navigate, location])

  return children
}

export default AuthGuard
