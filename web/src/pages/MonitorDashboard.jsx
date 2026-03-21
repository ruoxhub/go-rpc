import { useState, useEffect } from 'react'
import { Card, Row, Col, Statistic, Select, DatePicker, Spin, Alert, Empty } from 'antd'
import { Line, Bar, Pie } from '@ant-design/charts'
import axios from 'axios'
import dayjs from 'dayjs'

const { Option } = Select
const { RangePicker } = DatePicker

// 获取 API 基础路径
const getApiBase = () => {
  const host = window.location.hostname
  const port = window.location.port
  return `http://${host}:${port}/api`
}

function MonitorDashboard() {
  const [loading, setLoading] = useState(false)
  const [dashboardData, setDashboardData] = useState(null)
  const [timeRange, setTimeRange] = useState('hours')
  const [dateRange, setDateRange] = useState([dayjs().subtract(1, 'hours'), dayjs()])

  // 调用趋势数据
  const [invokeTrend, setInvokeTrend] = useState([])
  // QPS 分布数据
  const [qpsData, setQpsData] = useState([])
  // 设备状态数据
  const [deviceStatus, setDeviceStatus] = useState([])
  // 延迟百分位数据
  const [latencyPercentiles, setLatencyPercentiles] = useState([])

  const [error, setError] = useState(null)

  // 获取大盘数据
  const fetchDashboardData = async () => {
    try {
      const response = await axios.get(`${getApiBase()}/metrics/dashboard`)
      if (response.data.code === 0) {
        setDashboardData(response.data.data)
      }
    } catch (err) {
      console.error('获取大盘数据失败:', err)
    }
  }

  // 获取调用趋势
  const fetchInvokeTrend = async () => {
    try {
      const params = {
        name: 'invoke.total',
        timeRange: timeRange
      }
      const response = await axios.get(`${getApiBase()}/metrics`, { params })
      if (response.data.code === 0) {
        // 处理数据，转换为图表格式
        const trendData = response.data.data
          .filter(item => item.type === 'counter')
          .map(item => ({
            time: item.timeKey,
            value: item.value,
            type: '调用次数'
          }))
          .reverse() // 时间正序
        setInvokeTrend(trendData)
      }
    } catch (err) {
      console.error('获取调用趋势失败:', err)
    }
  }

  // 获取延迟百分位数
  const fetchLatencyPercentiles = async () => {
    try {
      const params = { timeRange }
      const response = await axios.get(`${getApiBase()}/metrics/latency/percentiles`, { params })
      if (response.data.code === 0) {
        const data = response.data.data.map(item => ({
          api: `${item.group}/${item.api}`,
          p50: item.p50 || 0,
          p90: item.p90 || 0,
          p99: item.p99 || 0,
        }))
        setLatencyPercentiles(data)
      }
    } catch (err) {
      console.error('获取延迟百分位失败:', err)
    }
  }

  // 获取设备状态
  const fetchDeviceStatus = async () => {
    try {
      const response = await axios.get(`${getApiBase()}/groups`)
      if (response.data.code === 0) {
        const groups = response.data.data || []
        let online = 0
        let offline = 0
        let disabled = 0

        groups.forEach(group => {
          if (group.devices) {
            group.devices.forEach(device => {
              if (device.disabled) {
                disabled++
              } else if (device.online) {
                online++
              } else {
                offline++
              }
            })
          }
        })

        setDeviceStatus([
          { type: '在线', value: online, color: '#52c41a' },
          { type: '离线', value: offline, color: '#d9d9d9' },
          { type: '禁用', value: disabled, color: '#ff4d4f' },
        ])
      }
    } catch (err) {
      console.error('获取设备状态失败:', err)
    }
  }

  // 获取 QPS 分布
  const fetchQpsData = async () => {
    try {
      const response = await axios.get(`${getApiBase()}/groups`)
      if (response.data.code === 0) {
        const groups = response.data.data || []
        const qps = groups.map(g => ({
          group: g.name,
          qps: g.qps || 0,
          currentQps: g.currentQps || 0,
        }))
        setQpsData(qps)
      }
    } catch (err) {
      console.error('获取 QPS 数据失败:', err)
    }
  }

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      setError(null)
      try {
        await Promise.all([
          fetchDashboardData(),
          fetchInvokeTrend(),
          fetchLatencyPercentiles(),
          fetchDeviceStatus(),
          fetchQpsData(),
        ])
      } catch (err) {
        setError('加载数据失败：' + err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [timeRange])

  // 调用趋势图配置
  const trendConfig = {
    data: invokeTrend,
    xField: 'time',
    yField: 'value',
    seriesField: 'type',
    smooth: true,
    height: 300,
    point: { size: 5, shape: 'circle' },
    yAxis: {
      label: {
        autoHide: true,
        autoRotate: false,
      },
    },
    tooltip: {
      showMarkers: true,
      shared: true,
    },
  }

  // QPS 分布图配置
  const qpsConfig = {
    data: qpsData,
    xField: 'group',
    yField: 'qps',
    seriesField: 'group',
    legend: { position: 'top' },
    height: 300,
    label: {
      style: { fill: '#aaa' },
    },
    tooltip: {
      showMarkers: true,
    },
  }

  // 设备状态饼图配置
  const devicePieConfig = {
    data: deviceStatus,
    angleField: 'value',
    colorField: 'type',
    radius: 0.8,
    height: 300,
    label: {
      type: 'outer',
      content: '{name} {percentage}',
    },
    color: ['#52c41a', '#d9d9d9', '#ff4d4f'],
    tooltip: {
      showMarkers: true,
    },
  }

  // 延迟百分位图配置
  const latencyConfig = {
    data: latencyPercentiles.flatMap(item => [
      { api: item.api, type: 'P50', value: item.p50 },
      { api: item.api, type: 'P90', value: item.p90 },
      { api: item.api, type: 'P99', value: item.p99 },
    ]),
    xField: 'api',
    yField: 'value',
    seriesField: 'type',
    isGroup: true,
    height: 300,
    label: {
      style: { fill: '#aaa' },
    },
    tooltip: {
      showMarkers: true,
    },
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 60 }}>
        <Spin size="large" tip="加载监控数据..." />
      </div>
    )
  }

  if (error) {
    return (
      <Alert
        type="error"
        message="加载失败"
        description={error}
        showIcon
      />
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>监控仪表盘</h2>
        <Select
          value={timeRange}
          onChange={(value) => setTimeRange(value)}
          style={{ width: 120 }}
        >
          <Option value="minutes">分钟</Option>
          <Option value="hours">小时</Option>
          <Option value="days">天</Option>
        </Select>
      </div>

      {/* 核心指标卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="总调用次数"
              value={dashboardData?.totalCalls || 0}
              suffix="次"
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="在线设备"
              value={dashboardData?.onlineDevices || 0}
              suffix="台"
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="分组总数"
              value={dashboardData?.totalGroups || 0}
              suffix="个"
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="用户总数"
              value={dashboardData?.totalUsers || 0}
              suffix="人"
              valueStyle={{ color: '#fa8c16' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 调用趋势图 */}
      <Card title="调用趋势" style={{ marginBottom: 24 }}>
        {invokeTrend.length > 0 ? (
          <Line {...trendConfig} />
        ) : (
          <Empty description="暂无调用数据" />
        )}
      </Card>

      {/* 延迟百分位对比 */}
      <Card title="API 延迟百分位数 (P50/P90/P99)" style={{ marginBottom: 24 }}>
        {latencyPercentiles.length > 0 ? (
          <Bar {...latencyConfig} />
        ) : (
          <Empty description="暂无延迟数据" />
        )}
      </Card>

      {/* QPS 分布和设备状态 */}
      <Row gutter={16}>
        <Col span={12}>
          <Card title="分组 QPS 配置">
            {qpsData.length > 0 ? (
              <Bar {...qpsConfig} />
            ) : (
              <Empty description="暂无分组数据" />
            )}
          </Card>
        </Col>
        <Col span={12}>
          <Card title="设备状态分布">
            {deviceStatus.some(d => d.value > 0) ? (
              <Pie {...devicePieConfig} />
            ) : (
              <Empty description="暂无设备数据" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default MonitorDashboard
