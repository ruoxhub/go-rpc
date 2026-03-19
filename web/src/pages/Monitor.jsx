import { useState } from 'react'
import { Tabs, Select, Card, Empty } from 'antd'

const { TabPane } = Tabs
const { Option } = Select

function Monitor() {
  const [timeRange, setTimeRange] = useState('hours')

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

      <Tabs defaultActiveKey="dashboard">
        <TabPane tab="业务大盘" key="dashboard">
          <Card title="调用量大盘" style={{ marginBottom: 24 }}>
            <Empty description="暂无数据" />
            {/* TODO: 添加图表组件 */}
          </Card>
          <Card title="在线设备 (前 5)">
            <Empty description="暂无数据" />
            {/* TODO: 添加图表组件 */}
          </Card>
        </TabPane>
        <TabPane tab="系统监控" key="system">
          <Card title="系统资源监控">
            <Empty description="暂无数据" />
            {/* TODO: 添加系统监控图表 */}
          </Card>
        </TabPane>
        <TabPane tab="MQL 编辑器" key="mql">
          <Card title="MQL 编辑器">
            <Empty description="暂无数据" />
            {/* TODO: 添加 MQL 编辑器 */}
          </Card>
        </TabPane>
        <TabPane tab="指标列表" key="metrics">
          <Card title="指标列表">
            <Empty description="暂无数据" />
            {/* TODO: 添加指标列表表格 */}
          </Card>
        </TabPane>
      </Tabs>
    </div>
  )
}

export default Monitor
