import { useEffect, useState } from 'react'
import { Alert, Card, Col, Empty, Row, Select, Spin, Statistic } from 'antd'
import ReactECharts from 'echarts-for-react'
import { groupApi, metricApi } from '../utils/api'

const { Option } = Select

function MonitorDashboard() {
  const [loading, setLoading] = useState(false)
  const [timeRange, setTimeRange] = useState('hours')
  const [dashboardData, setDashboardData] = useState(null)
  const [invokeTrend, setInvokeTrend] = useState([])
  const [deviceStatus, setDeviceStatus] = useState([])
  const [latencyPercentiles, setLatencyPercentiles] = useState([])
  const [groupQps, setGroupQps] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError('')
      try {
        const [dashboard, metrics, latency, groups] = await Promise.all([
          metricApi.getDashboard(),
          metricApi.getMetrics({ name: 'invoke.total', timeRange }),
          metricApi.getLatencyPercentiles({ timeRange }),
          groupApi.list()
        ])

        setDashboardData(dashboard.data || null)
        setInvokeTrend((metrics.data || []).slice().reverse())
        setLatencyPercentiles(latency.data || [])

        const groupList = groups.data || []
        setGroupQps(groupList.map((group) => ({
          name: group.groupName,
          value: group.quotaQpsGroup || 0
        })))

        const online = groupList.reduce((sum, group) => sum + (group.availableClients || 0), 0)
        const disabled = groupList.reduce((sum, group) => sum + (group.disabledClients || 0), 0)
        setDeviceStatus([
          { name: '在线', value: online },
          { name: '离线/禁用', value: disabled }
        ])
      } catch (err) {
        setError(err.response?.data?.message || err.message || '加载监控数据失败')
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [timeRange])

  if (loading && !dashboardData) {
    return (
      <div style={{ textAlign: 'center', padding: 60 }}>
        <Spin size="large" tip="加载监控数据..." />
      </div>
    )
  }

  if (error) {
    return <Alert type="error" showIcon message="加载失败" description={error} />
  }

  const trendOption = {
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: invokeTrend.map((item) => item.timeKey)
    },
    yAxis: { type: 'value' },
    series: [
      {
        name: '调用量',
        type: 'line',
        smooth: true,
        data: invokeTrend.map((item) => item.value)
      }
    ]
  }

  const latencyOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['P50', 'P90', 'P99'] },
    xAxis: {
      type: 'category',
      data: latencyPercentiles.map((item) => `${item.group}/${item.api}`)
    },
    yAxis: { type: 'value' },
    series: [
      { name: 'P50', type: 'bar', data: latencyPercentiles.map((item) => item.p50 || 0) },
      { name: 'P90', type: 'bar', data: latencyPercentiles.map((item) => item.p90 || 0) },
      { name: 'P99', type: 'bar', data: latencyPercentiles.map((item) => item.p99 || 0) }
    ]
  }

  const groupQpsOption = {
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: groupQps.map((item) => item.name)
    },
    yAxis: { type: 'value' },
    series: [
      {
        type: 'bar',
        data: groupQps.map((item) => item.value)
      }
    ]
  }

  const deviceStatusOption = {
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'pie',
        radius: '70%',
        data: deviceStatus
      }
    ]
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>监控仪表盘</h2>
        <Select value={timeRange} onChange={setTimeRange} style={{ width: 120 }}>
          <Option value="minutes">分钟</Option>
          <Option value="hours">小时</Option>
          <Option value="days">天</Option>
        </Select>
      </div>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="总调用次数" value={dashboardData?.totalCalls || 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="在线设备" value={dashboardData?.onlineDevices || 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="分组总数" value={dashboardData?.totalGroups || 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="用户总数" value={dashboardData?.totalUsers || 0} />
          </Card>
        </Col>
      </Row>

      <Card title="调用趋势" style={{ marginBottom: 24 }}>
        {invokeTrend.length ? <ReactECharts option={trendOption} style={{ height: 320 }} /> : <Empty description="暂无调用数据" />}
      </Card>

      <Card title="延迟百分位" style={{ marginBottom: 24 }}>
        {latencyPercentiles.length ? <ReactECharts option={latencyOption} style={{ height: 320 }} /> : <Empty description="暂无延迟数据" />}
      </Card>

      <Row gutter={16}>
        <Col span={12}>
          <Card title="分组 QPS 配额">
            {groupQps.length ? <ReactECharts option={groupQpsOption} style={{ height: 320 }} /> : <Empty description="暂无分组数据" />}
          </Card>
        </Col>
        <Col span={12}>
          <Card title="设备状态">
            {deviceStatus.some((item) => item.value > 0) ? <ReactECharts option={deviceStatusOption} style={{ height: 320 }} /> : <Empty description="暂无设备数据" />}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default MonitorDashboard
