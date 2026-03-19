import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './layouts/Layout'
import Dashboard from './pages/Dashboard'
import GroupList from './pages/GroupList'
import AnonymousGroup from './pages/AnonymousGroup'
import Monitor from './pages/Monitor'
import UserList from './pages/UserList'
import SystemPanel from './pages/SystemPanel'
import GroupDetail from './pages/GroupDetail'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="groups" element={<GroupList />} />
          <Route path="anonymous-groups" element={<AnonymousGroup />} />
          <Route path="monitor" element={<Monitor />} />
          <Route path="users" element={<UserList />} />
          <Route path="system" element={<SystemPanel />} />
          <Route path="group/:groupName" element={<GroupDetail />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
