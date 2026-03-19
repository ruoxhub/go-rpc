import { useState } from 'react'
import { Card, Empty, Select } from 'antd'

const { Option } = Select

function GroupMonitor({ groupName }) {
  const [timeRange, setTimeRange] = useState('hours')

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
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

      <Card title="group 监控" style={{ marginBottom: 24 }}>
        {/* TODO: 添加 group 监控图表 */}
        <Empty description="暂无监控数据" />
      </Card>

      <Card title="在线设备">
        {/* TODO: 添加在线设备图表 */}
        <Empty description="暂无在线设备" />
      </Card>
    </div>
  )
}

export default GroupMonitor
