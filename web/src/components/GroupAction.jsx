import { useState } from 'react'
import { Card, Empty, Select } from 'antd'

const { Option } = Select

function GroupAction({ groupName }) {
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

      <Card title={`action 监控：${groupName}`}>
        {/* TODO: 添加 action 监控图表 */}
        <Empty description="暂无 action 数据" />
      </Card>
    </div>
  )
}

export default GroupAction
