import axios from 'axios'
import { message } from 'antd'

const defaultHeaders = {
  'Content-Type': 'application/json'
}

const businessApi = axios.create({
  baseURL: '/business',
  timeout: 30000,
  headers: defaultHeaders
})

const adminApi = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: defaultHeaders
})

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: defaultHeaders
})

const handleAuthFailure = () => {
  localStorage.removeItem('api_token')
  localStorage.removeItem('login_token')
  if (window.location.pathname !== '/login') {
    window.location.replace('/login')
  }
}

const setupRequestInterceptor = (apiInstance) => {
  apiInstance.interceptors.request.use(
    (config) => {
      const token = localStorage.getItem('api_token')
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
      return config
    },
    (error) => Promise.reject(error)
  )
}

const setupResponseInterceptor = (apiInstance) => {
  apiInstance.interceptors.response.use(
    (response) => response.data,
    (error) => {
      const status = error.response?.status
      const errorMsg = error.response?.data?.message || error.message || '请求失败'

      if (status === 401) {
        handleAuthFailure()
      }

      if (status === 403) {
        if (!error.config?.silent) {
          message.error('权限不足')
        }
        return Promise.reject(error)
      }

      if (!error.config?.silent) {
        message.error(errorMsg)
      }

      return Promise.reject(error)
    }
  )
}

setupRequestInterceptor(businessApi)
setupResponseInterceptor(businessApi)
setupRequestInterceptor(adminApi)
setupResponseInterceptor(adminApi)
setupRequestInterceptor(apiClient)
setupResponseInterceptor(apiClient)

export const groupApi = {
  list: () => adminApi.get('/groups'),
  create: (data) => adminApi.post('/groups', data),
  delete: (data) => adminApi.delete('/groups', { data }),
  getDetail: (groupName) => adminApi.get(`/groups/${groupName}`),
  updateQps: (data) => adminApi.put('/groups/qps', data),
  getDevices: (groupName) => adminApi.get(`/groups/${groupName}/devices`),
  deleteDevice: (data) => adminApi.delete('/groups/devices', { data }),
  disableDevice: (data) => adminApi.put('/groups/devices/disable', data),
  getActions: (groupName) => adminApi.get(`/groups/${groupName}/actions`),
  addAction: (data) => adminApi.post('/groups/actions', data),
  deleteAction: (data) => adminApi.delete('/groups/actions', { data })
}

export const userApi = {
  list: () => adminApi.get('/users'),
  add: (data) => adminApi.post('/users', data),
  updateQps: (data) => adminApi.put('/users/qps', data),
  delete: (data) => adminApi.delete('/users', { data }),
  getCurrentUser: () => adminApi.get('/current'),
  changePassword: (data) => adminApi.post('/current/password', data),
  refreshToken: () => adminApi.post('/current/token/refresh')
}

export const sysConfigApi = {
  list: () => adminApi.get('/sysconfig'),
  update: (data) => adminApi.put('/sysconfig', data),
  getNodes: () => adminApi.get('/sysconfig/nodes'),
  getLogs: (params) => adminApi.get('/sysconfig/logs', { params }),
  getAppLogs: (params) => adminApi.get('/sysconfig/app-logs', { params })
}

export const anonymousGroupApi = {
  list: () => adminApi.get('/anonymous-groups'),
  delete: (data) => adminApi.delete('/anonymous-groups', { data }),
  convert: (data) => adminApi.post('/anonymous-groups/convert', data)
}

export const metricApi = {
  getMetrics: (params) => adminApi.get('/metrics', { params }),
  getMetricList: () => adminApi.get('/metrics/list'),
  getDashboard: () => adminApi.get('/metrics/dashboard'),
  getLatencyPercentiles: (params) => adminApi.get('/metrics/latency/percentiles', { params })
}

export const traceApi = {
  getTraces: (params) => apiClient.get('/traces', { params }),
  getTraceDetail: (traceId) => apiClient.get(`/traces/${traceId}`),
  getTraceStats: (params) => apiClient.get('/traces/stats', { params }),
  getTraceTimeline: (params) => apiClient.get('/traces/timeline', { params }),
  getTraceExtraData: (traceId) => apiClient.get(`/traces/${traceId}/extra`)
}

export const alertApi = {
  getRules: (params) => apiClient.get('/alerts/rules', { params }),
  getRule: (id) => apiClient.get(`/alerts/rules/${id}`),
  createRule: (data) => apiClient.post('/alerts/rules', data),
  updateRule: (id, data) => apiClient.put(`/alerts/rules/${id}`, data),
  deleteRule: (id) => apiClient.delete(`/alerts/rules/${id}`),
  getHistory: (params) => apiClient.get('/alerts/history', { params })
}

// 前端兼容 API 封装（/sekiro-api/frontend/*）
export const frontendApi = {
  listGroup: () => apiClient.get('/sekiro-api/frontend/listGroup'),
  anonymousGroupList: () => apiClient.get('/sekiro-api/frontend/anonymousGroupList'),
  groupDetail: (groupName) => apiClient.get('/sekiro-api/frontend/groupDetail', {
    params: { groupName }
  })
}

export { adminApi, apiClient, handleAuthFailure }

export default businessApi
