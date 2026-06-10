import { useState, useEffect } from 'react'
import { Card, Empty, Select, Spin, Row, Col, Statistic, Alert, Button } from 'antd'
import * as echarts from 'echarts'
import ReactECharts from 'echarts-for-react'
import { metricApi } from '../utils/api'

const { Option } = Select

function GroupMonitor({ groupName }) {
  const [timeRange, setTimeRange] = useState('hours')
  const [loading, setLoading] = useState(false)
  const [metricsData, setMetricsData] = useState([])
  const [dashboardData, setDashboardData] = useState(null)
  const [dashboardLoading, setDashboardLoading] = useState(false)
  const [dashboardError, setDashboardError] = useState(false)

  // 加载监控数据
  const loadMetrics = async () => {
    setLoading(true)
    try {
      const result = await metricApi.getMetrics({
        name: groupName,
        timeRange: timeRange
      })
      setMetricsData(result.data || [])
    } catch (error) {
      console.error('加载监控数据失败:', error)
    } finally {
      setLoading(false)
    }
  }

  // 加载大盘数据
  const loadDashboard = async () => {
    setDashboardLoading(true)
    setDashboardError(false)
    try {
      const result = await metricApi.getDashboard()
      setDashboardData(result.data)
    } catch (error) {
      console.error('加载大盘数据失败:', error)
      setDashboardError(true)
      // 不显示错误提示，仅记录日志
    } finally {
      setDashboardLoading(false)
    }
  }

  useEffect(() => {
    loadMetrics()
    loadDashboard()
  }, [groupName, timeRange])

  // 调用量趋势图表配置
  const callTrendOption = () => {
    const sortedData = [...metricsData].reverse()
    const timeLabels = sortedData.map(m => {
      const timeKey = m.timeKey
      if (timeRange === 'minutes') {
        return timeKey.substring(11, 16) // HH:mm
      } else if (timeRange === 'hours') {
        return timeKey.substring(0, 13) + ':00' // MM-DD HH:00
      } else {
        return timeKey.substring(0, 10) // YYYY-MM-DD
      }
    })
    const values = sortedData.map(m => m.value)

    return {
      title: {
        text: '调用量趋势',
        left: 'center',
        textStyle: {
          fontSize: 14,
          fontWeight: 'bold'
        }
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'shadow'
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: timeLabels,
        axisLabel: {
          rotate: timeRange === 'minutes' ? 0 : 45,
          interval: timeRange === 'minutes' ? 'auto' : 0
        }
      },
      yAxis: {
        type: 'value',
        name: '调用次数'
      },
      series: [
        {
          name: '调用量',
          type: 'bar',
          data: values,
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '#83bff6' },
              { offset: 0.5, color: '#188df0' },
              { offset: 1, color: '#188df0' }
            ])
          },
          showBackground: true,
          backgroundStyle: {
            color: 'rgba(180, 180, 180, 0.1)'
          }
        }
      ]
    }
  }

  // 在线设备状态图表配置
  const deviceStatusOption = () => {
    const onlineCount = dashboardData?.onlineDevices || 0
    const offlineCount = (dashboardData?.totalGroups || 0) * 5 - onlineCount

    return {
      title: {
        text: '设备在线状态',
        left: 'center',
        textStyle: {
          fontSize: 14,
          fontWeight: 'bold'
        }
      },
      tooltip: {
        trigger: 'item'
      },
      legend: {
        orient: 'vertical',
        left: 'left',
        top: 'middle'
      },
      series: [
        {
          name: '设备状态',
          type: 'pie',
          radius: '50%',
          data: [
            { value: onlineCount, name: '在线设备', itemStyle: { color: '#52c41a' } },
            { value: offlineCount, name: '离线设备', itemStyle: { color: '#d9d9d9' } }
          ],
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.5)'
            }
          },
          label: {
            formatter: '{b}: {c} ({d}%)'
          }
        }
      ]
    }
  }

  // QPS 趋势图表配置
  const qpsTrendOption = () => {
    const qpsData = metricsData.filter(m => m.type === 'qps')
    const sortedData = [...qpsData].reverse()
    const timeLabels = sortedData.map(m => {
      const timeKey = m.timeKey
      if (timeRange === 'minutes') {
        return timeKey.substring(11, 16)
      } else if (timeRange === 'hours') {
        return timeKey.substring(0, 13) + ':00'
      } else {
        return timeKey.substring(0, 10)
      }
    })
    const values = sortedData.map(m => m.value)

    return {
      title: {
        text: 'QPS 趋势',
        left: 'center',
        textStyle: {
          fontSize: 14,
          fontWeight: 'bold'
        }
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'line'
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: timeLabels,
        axisLabel: {
          rotate: timeRange === 'minutes' ? 0 : 45,
          interval: timeRange === 'minutes' ? 'auto' : 0
        }
      },
      yAxis: {
        type: 'value',
        name: 'QPS'
      },
      series: [
        {
          name: 'QPS',
          type: 'line',
          smooth: true,
          data: values,
          itemStyle: {
            color: '#1890ff'
          },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(24,144,255,0.3)' },
              { offset: 1, color: 'rgba(24,144,255,0.01)' }
            ])
          },
          lineStyle: {
            width: 3
          }
        }
      ]
    }
  }

  if (loading && !metricsData.length) {
    return (
      <div style={{ textAlign: 'center', padding: 60 }}>
        <Spin size="large" tip="加载监控数据中..." />
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Select
          value={timeRange}
          onChange={(value) => setTimeRange(value)}
          style={{ width: 150 }}
          size="large"
        >
          <Option value="minutes">分钟</Option>
          <Option value="hours">小时</Option>
          <Option value="days">天</Option>
        </Select>
      </div>

      {/* 概览统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card>
            <Statistic
              title="总调用量"
              value={dashboardLoading ? undefined : (dashboardData?.totalCalls || 0)}
              suffix="次"
              valueStyle={{ color: '#1890ff' }}
              loading={dashboardLoading}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="在线设备"
              value={dashboardLoading ? undefined : (dashboardData?.onlineDevices || 0)}
              suffix="台"
              valueStyle={{ color: '#52c41a' }}
              loading={dashboardLoading}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="分组数量"
              value={dashboardLoading ? undefined : (dashboardData?.totalGroups || 0)}
              suffix="个"
              valueStyle={{ color: '#722ed1' }}
              loading={dashboardLoading}
            />
          </Card>
        </Col>
      </Row>

      {dashboardError && !dashboardLoading && (
        <Alert
          message="大盘数据加载失败"
          description="部分概览数据可能无法显示，请刷新页面重试"
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          action={
            <Button size="small" onClick={loadDashboard}>
              重试
            </Button>
          }
        />
      )}

      {/* 调用量趋势图表 */}
      <Card title="调用量趋势" style={{ marginBottom: 24 }}>
        {metricsData.length > 0 ? (
          <ReactECharts
            option={callTrendOption()}
            style={{ height: 350 }}
            opts={{ renderer: 'canvas' }}
          />
        ) : (
          <Empty description="暂无调用量数据" />
        )}
      </Card>

      {/* QPS 趋势和在线设备状态 */}
      <Row gutter={16}>
        <Col span={16}>
          <Card title="QPS 趋势">
            {metricsData.filter(m => m.type === 'qps').length > 0 ? (
              <ReactECharts
                option={qpsTrendOption()}
                style={{ height: 300 }}
                opts={{ renderer: 'canvas' }}
              />
            ) : (
              <Empty description="暂无 QPS 数据" />
            )}
          </Card>
        </Col>
        <Col span={8}>
          <Card title="在线设备状态" style={{ height: 300 }}>
            <ReactECharts
              option={deviceStatusOption()}
              style={{ height: 260 }}
              opts={{ renderer: 'canvas' }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default GroupMonitor
