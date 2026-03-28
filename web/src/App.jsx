import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './layouts/Layout'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import GroupList from './pages/GroupList'
import AnonymousGroup from './pages/AnonymousGroup'
import MonitorDashboard from './pages/MonitorDashboard'
import UserList from './pages/UserList'
import SystemPanel from './pages/SystemPanel'
import GroupDetail from './pages/GroupDetail'
import TraceList from './pages/TraceList'
import TraceDetail from './pages/TraceDetail'
import AlertRules from './pages/AlertRules'
import AlertHistory from './pages/AlertHistory'
import AuthGuard from './components/AuthGuard'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* 登录页面（不需要认证） */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* 需要认证的路由 */}
        <Route
          path="/"
          element={
            <AuthGuard>
              <Layout />
            </AuthGuard>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="groups" element={<GroupList />} />
          <Route path="anonymous-groups" element={<AnonymousGroup />} />
          <Route path="monitor" element={<MonitorDashboard />} />
          <Route path="users" element={<UserList />} />
          <Route path="system" element={<SystemPanel />} />
          <Route path="group/:groupName" element={<GroupDetail />} />
          <Route path="traces" element={<TraceList />} />
          <Route path="traces/:traceId" element={<TraceDetail />} />
          <Route path="alerts" element={<AlertRules />} />
          <Route path="alert-history" element={<AlertHistory />} />
        </Route>

        {/* 兜底路由：未匹配的路径跳转到首页 */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
