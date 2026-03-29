import { useState, useEffect } from 'react'
import { Tabs, Select, Card, Empty, Table, Statistic, Row, Col, Spin } from 'antd'
import ReactECharts from 'echarts-for-react'
import { metricApi } from '../utils/api'

const { TabPane } = Tabs
const { Option } = Select

// 调用量大盘组件
function CallTrendChart({ data, timeRange }) {
  if (!data || data.length === 0) {
    return <Empty description="暂无调用量数据" />
  }

  // 按时间排序
  const sortedData = [...data].sort((a, b) => a.timeKey.localeCompare(b.timeKey))

  const option = {
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const time = params[0]?.axisValue || ''
        const total = params.reduce((sum, p) => sum + p.value, 0)
        return `${time}<br/>总调用量：${total.toFixed(0)}`
      }
    },
    xAxis: {
      type: 'category',
      data: sortedData.map(item => item.timeKey),
      axisLabel: {
        rotate: timeRange === 'days' ? 45 : 0
      }
    },
    yAxis: {
      type: 'value',
      name: '调用次数'
    },
    series: [{
      data: sortedData.map(item => item.value),
      type: 'line',
      smooth: true,
      areaStyle: {
        opacity: 0.3
      },
      itemStyle: {
        color: '#1890ff'
      }
    }],
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    }
  }

  return <ReactECharts option={option} style={{ height: 300 }} />
}

// 延迟分析组件
function LatencyChart({ data }) {
  if (!data || data.length === 0) {
    return <Empty description="暂无延迟数据" />
  }

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' }
    },
    legend: {
      data: ['P50', 'P90', 'P99']
    },
    xAxis: {
      type: 'category',
      data: data.map(item => item.api || '默认'),
      axisLabel: { rotate: 45 }
    },
    yAxis: {
      type: 'value',
      name: '延迟 (ms)'
    },
    series: [
      {
        name: 'P50',
        type: 'bar',
        data: data.map(item => item.p50 || 0),
        itemStyle: { color: '#52c41a' }
      },
      {
        name: 'P90',
        type: 'bar',
        data: data.map(item => item.p90 || 0),
        itemStyle: { color: '#faad14' }
      },
      {
        name: 'P99',
        type: 'bar',
        data: data.map(item => item.p99 || 0),
        itemStyle: { color: '#ff4d4f' }
      }
    ],
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    }
  }

  return <ReactECharts option={option} style={{ height: 300 }} />
}

// 在线设备趋势组件
function OnlineDevicesChart({ data }) {
  const option = {
    tooltip: {
      trigger: 'axis'
    },
    xAxis: {
      type: 'category',
      data: data.map(item => item.timeKey)
    },
    yAxis: {
      type: 'value',
      name: '设备数'
    },
    series: [{
      data: data.map(item => item.value),
      type: 'line',
      smooth: true,
      itemStyle: { color: '#722ed1' }
    }],
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    }
  }

  return <ReactECharts option={option} style={{ height: 200 }} />
}

function Monitor() {
  const [timeRange, setTimeRange] = useState('hours')
  const [loading, setLoading] = useState(false)
  const [dashboardData, setDashboardData] = useState(null)
  const [callTrendData, setCallTrendData] = useState([])
  const [latencyData, setLatencyData] = useState([])
  const [metricList, setMetricList] = useState([])

  // 加载大盘数据
  const loadDashboard = async () => {
    try {
      const res = await metricApi.getDashboard()
      if (res.code === 0) {
        setDashboardData(res.data)
      }
    } catch (error) {
      console.error('Failed to load dashboard:', error)
    }
  }

  // 加载调用趋势数据
  const loadCallTrend = async () => {
    try {
      const res = await metricApi.getMetrics({
        name: 'invoke.total',
        timeRange: timeRange
      })
      if (res.code === 0) {
        setCallTrendData(res.data || [])
      }
    } catch (error) {
      console.error('Failed to load call trend:', error)
    }
  }

  // 加载延迟数据
  const loadLatency = async () => {
    try {
      const res = await metricApi.getLatencyPercentiles({})
      if (res.code === 0) {
        setLatencyData(res.data || [])
      }
    } catch (error) {
      console.error('Failed to load latency:', error)
    }
  }

  // 加载指标列表
  const loadMetricList = async () => {
    try {
      const res = await metricApi.getMetricList()
      if (res.code === 0) {
        setMetricList(res.data || [])
      }
    } catch (error) {
      console.error('Failed to load metric list:', error)
    }
  }

  useEffect(() => {
    setLoading(true)
    Promise.all([
      loadDashboard(),
      loadCallTrend(),
      loadLatency(),
      loadMetricList()
    ]).finally(() => setLoading(false))
  }, [timeRange])

  // 指标列表表格列定义
  const metricColumns = [
    {
      title: '指标名称',
      dataIndex: 'name',
      key: 'name'
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type) => {
        const color = type === 'counter' ? '#1890ff' : '#52c41a'
        return <span style={{ color }}>{type === 'counter' ? '计数器' : '延迟'}</span>
      }
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      render: (tags) => (tags || []).join(', ')
    }
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>监控指标</h2>
        <Select
          value={timeRange}
          onChange={(value) => setTimeRange(value)}
          style={{ width: 150 }}
        >
          <Option value="minutes">分钟</Option>
          <Option value="hours">小时</Option>
          <Option value="days">天</Option>
        </Select>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin size="large" tip="加载中..." />
        </div>
      ) : (
        <>
          {/* 大盘卡片 */}
          <Card style={{ marginBottom: 24 }}>
            <Row gutter={16}>
              <Col span={6}>
                <Statistic
                  title="总调用量"
                  value={dashboardData?.totalCalls || 0}
                  suffix="次"
                  valueStyle={{ color: '#1890ff' }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="在线设备"
                  value={dashboardData?.onlineDevices || 0}
                  suffix="台"
                  valueStyle={{ color: '#52c41a' }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="分组数量"
                  value={dashboardData?.totalGroups || 0}
                  suffix="个"
                  valueStyle={{ color: '#722ed1' }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="用户数量"
                  value={dashboardData?.totalUsers || 0}
                  suffix="人"
                  valueStyle={{ color: '#faad14' }}
                />
              </Col>
            </Row>
          </Card>

          <Tabs defaultActiveKey="dashboard">
            <TabPane tab="业务大盘" key="dashboard">
              <Card title="调用量趋势" style={{ marginBottom: 24 }}>
                <CallTrendChart data={callTrendData} timeRange={timeRange} />
              </Card>
              <Card title="延迟分析 (P50/P90/P99)">
                <LatencyChart data={latencyData} />
              </Card>
            </TabPane>
            <TabPane tab="系统监控" key="system">
              <Card title="系统资源监控">
                <Empty description="系统资源监控待实现" />
              </Card>
            </TabPane>
            <TabPane tab="MQL 编辑器" key="mql">
              <Card title="MQL 编辑器">
                <Empty description="MQL 编辑器待实现" />
              </Card>
            </TabPane>
            <TabPane tab="指标列表" key="metrics">
              <Card title="指标列表">
                <Table
                  columns={metricColumns}
                  dataSource={metricList}
                  rowKey="id"
                  pagination={{ pageSize: 20 }}
                />
              </Card>
            </TabPane>
          </Tabs>
        </>
      )}
    </div>
  )
}

export default Monitor
