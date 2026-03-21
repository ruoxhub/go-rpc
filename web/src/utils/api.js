import axios from 'axios'
import { message } from 'antd'

// 创建三个 API 实例：business、管理 API、以及通用 API
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

// 通用 API 实例（用于追踪、告警等新功能）
const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 统一的请求拦截器
const setupRequestInterceptor = (apiInstance) => {
  apiInstance.interceptors.request.use(
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
}

// 统一的响应拦截器
const setupResponseInterceptor = (apiInstance) => {
  apiInstance.interceptors.response.use(
    (response) => {
      return response.data
    },
    (error) => {
      const errorMsg = error.response?.data?.message || error.message || '请求失败'
      console.error('API Error:', errorMsg)
      // 非静默请求显示错误提示
      if (!error.config?.silent) {
        message.error(errorMsg)
      }
      return Promise.reject(error)
    }
  )
}

// 为所有实例设置拦截器
setupRequestInterceptor(businessApi)
setupResponseInterceptor(businessApi)
setupRequestInterceptor(adminApi)
setupResponseInterceptor(adminApi)
setupRequestInterceptor(apiClient)
setupResponseInterceptor(apiClient)

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
  getMetrics: (params) => adminApi.get('/metrics', { params }),
  getMetricList: () => adminApi.get('/metrics/list'),
  getDashboard: () => adminApi.get('/metrics/dashboard'),
  getLatencyPercentiles: (params) => adminApi.get('/metrics/latency/percentiles', { params })
}

// 追踪查询 API
export const traceApi = {
  getTraces: (params) => apiClient.get('/traces', { params }),
  getTraceDetail: (traceId) => apiClient.get(`/traces/${traceId}`),
  getTraceStats: (params) => apiClient.get('/traces/stats', { params }),
  getTraceTimeline: (params) => apiClient.get('/traces/timeline', { params }),
  getTraceExtraData: (traceId) => apiClient.get(`/traces/${traceId}/extra`)
}

// 告警管理 API
export const alertApi = {
  // 告警规则
  getRules: (params) => apiClient.get('/alerts/rules', { params }),
  getRule: (id) => apiClient.get(`/alerts/rules/${id}`),
  createRule: (data) => apiClient.post('/alerts/rules', data),
  updateRule: (id, data) => apiClient.put(`/alerts/rules/${id}`, data),
  deleteRule: (id) => apiClient.delete(`/alerts/rules/${id}`),
  // 告警历史
  getHistory: (params) => apiClient.get('/alerts/history', { params })
}

export default businessApi
