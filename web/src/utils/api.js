import axios from 'axios'
import { message } from 'antd'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('api_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error.response?.status
    const body = error.response?.data
    // 服务端统一信封: { code, message, data, trace_id, ... }
    // 业务错误可能是 HTTP 2xx (3xxx 业务码) 或 4xx/5xx, 都从 body.message 取文案。
    const errorMsg = body?.message || error.message || '请求失败'

    if (status === 401 || body?.code === 2001 || body?.code === 2002) {
      localStorage.removeItem('api_token')
      localStorage.removeItem('login_token')
      if (window.location.pathname !== '/login') {
        window.location.replace('/login')
      }
    }

    if ((status === 403 || body?.code === 2003) && !error.config?.silent) {
      message.error('权限不足')
      return Promise.reject(error)
    }

    if (!error.config?.silent) {
      message.error(errorMsg)
    }

    return Promise.reject(error)
  }
)

export const groupApi = {
  list: () => api.get('/groups'),
  create: (data) => api.post('/groups', data),
  delete: (data) => api.delete('/groups', { data }),
  getDetail: (groupName) => api.get(`/groups/${groupName}`),
  updateQps: (data) => api.put('/groups/qps', data),
  getDevices: (groupName) => api.get(`/groups/${groupName}/devices`),
  deleteDevice: (data) => api.delete('/groups/devices', { data }),
  getActions: (groupName) => api.get(`/groups/${groupName}/actions`),
  addAction: (data) => api.post('/groups/actions', data),
  deleteAction: (data) => api.delete('/groups/actions', { data }),
  batchDelete: (groupNames) => api.post('/groups/batch/delete', { groupNames }),
  batchUpdateQps: (data) => api.put('/groups/batch/qps', data)
}

export const userApi = {
  list: () => api.get('/users'),
  add: (data) => api.post('/users', data),
  updateQps: (data) => api.put('/users/qps', data),
  delete: (data) => api.delete('/users', { data }),
  getCurrentUser: () => api.get('/current'),
  changePassword: (data) => api.post('/current/password', data),
  refreshToken: () => api.post('/current/token/refresh')
}

export const sysConfigApi = {
  list: () => api.get('/sysconfig'),
  update: (data) => api.put('/sysconfig', data),
  getNodes: () => api.get('/sysconfig/nodes'),
  getLogs: (params) => api.get('/sysconfig/logs', { params }),
  getAppLogs: (params) => api.get('/sysconfig/app-logs', { params })
}

export const metricApi = {
  getMetrics: (params) => api.get('/metrics', { params }),
  getMetricList: () => api.get('/metrics/list'),
  getDashboard: () => api.get('/metrics/dashboard'),
  getLatencyPercentiles: (params) => api.get('/metrics/latency/percentiles', { params })
}

export const traceApi = {
  getTraces: (params) => api.get('/traces', { params }),
  getTraceDetail: (traceId) => api.get(`/traces/${traceId}`),
  getTraceStats: (params) => api.get('/traces/stats', { params }),
  getTraceTimeline: (params) => api.get('/traces/timeline', { params }),
  getTraceExtraData: (traceId) => api.get(`/traces/${traceId}/extra`)
}

export const alertApi = {
  getRules: (params) => api.get('/alerts/rules', { params }),
  getRule: (id) => api.get(`/alerts/rules/${id}`),
  createRule: (data) => api.post('/alerts/rules', data),
  updateRule: (id, data) => api.put(`/alerts/rules/${id}`, data),
  deleteRule: (id) => api.delete(`/alerts/rules/${id}`),
  getHistory: (params) => api.get('/alerts/history', { params })
}

export const frontendApi = {
  listGroup: () => api.get('/rpc-api/frontend/listGroup'),
  groupDetail: (groupName) => api.get('/rpc-api/frontend/groupDetail', {
    params: { groupName }
  })
}
