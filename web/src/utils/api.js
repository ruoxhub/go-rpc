import axios from 'axios'

// 创建两个 API 实例：一个用于 business 接口，一个用于管理 API
const businessApi = axios.create({
  baseURL: '/business',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 管理 API（用户、分组、系统配置等）
const adminApi = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器 - businessApi
businessApi.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('api_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 请求拦截器 - adminApi
adminApi.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('api_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器 - businessApi
businessApi.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    console.error('API Error:', error)
    throw error
  }
)

// 响应拦截器 - adminApi
adminApi.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    console.error('API Error:', error)
    throw error
  }
)

// 分组管理 API
export const groupApi = {
  // 获取分组列表
  list: () => adminApi.get('/groups'),
  // 创建分组
  create: (data) => adminApi.post('/groups', data),
  // 删除分组
  delete: (data) => adminApi.delete('/groups', { data }),
  // 获取分组详情
  getDetail: (groupName) => adminApi.get(`/groups/${groupName}`),
  // 更新分组 QPS
  updateQps: (data) => adminApi.put('/groups/qps', data),
  // 获取设备列表
  getDevices: (groupName) => adminApi.get(`/groups/${groupName}/devices`),
  // 删除设备
  deleteDevice: (data) => adminApi.delete('/groups/devices', { data }),
  // 禁用/启用设备
  disableDevice: (data) => adminApi.put('/groups/devices/disable', data),
  // 获取 Action 列表
  getActions: (groupName) => adminApi.get(`/groups/${groupName}/actions`),
  // 添加 Action
  addAction: (data) => adminApi.post('/groups/actions', data),
  // 删除 Action
  deleteAction: (data) => adminApi.delete('/groups/actions', { data })
}

// 用户管理 API
export const userApi = {
  list: () => adminApi.get('/users'),
  add: (data) => adminApi.post('/users', data),
  updateQps: (data) => adminApi.put('/users/qps', data),
  delete: (data) => adminApi.delete('/users', { data }),
  getCurrentUser: () => adminApi.get('/current'),
  changePassword: (data) => adminApi.post('/current/password', data),
  refreshToken: () => adminApi.post('/current/token/refresh')
}

// 系统配置 API
export const sysConfigApi = {
  list: () => adminApi.get('/sysconfig'),
  update: (data) => adminApi.put('/sysconfig', data),
  getNodes: () => adminApi.get('/sysconfig/nodes'),
  getLogs: () => adminApi.get('/sysconfig/logs')
}

// 匿名分组 API
export const anonymousGroupApi = {
  list: () => adminApi.get('/anonymous-groups')
}

// 监控指标 API
export const metricApi = {
  getMetrics: () => adminApi.get('/metrics'),
  getMetricList: () => adminApi.get('/metrics/list'),
  getDashboard: () => adminApi.get('/metrics/dashboard')
}

export default businessApi
