# 分组功能完善计划

## 背景

Sekiro RPC Go 实现已具备基础的分组管理功能，包括：
- 后端：分组 CRUD API、设备管理、Action 查询
- 前端：分组列表、分组详情页面（含基础信息、监控、Action、设备列表标签页）
- 数据库：group_config、group_device、group_actions 表

但当前实现存在以下问题：
1. **前端使用模拟数据**，未与后端 API 对接
2. **创建分组功能未实现**（仅提示信息）
3. **删除功能未调用真实 API**
4. **QPS 编辑保存功能未实现**
5. **设备列表、Action 管理组件使用模拟数据**
6. **缺少 Action 添加/删除功能**
7. **设备状态实时更新缺失**

## 完善目标

### 1. 前端与后端 API 对接

**分组列表页面 (GroupList.jsx)**
- 调用 `GET /api/groups` 获取真实分组列表
- 实现创建分组对话框，调用 `POST /api/groups`
- 删除功能调用 `DELETE /api/groups`
- 搜索功能改为服务端搜索

**分组详情页面 (GroupDetail.jsx)**
- 调用 `GET /api/groups/:groupName` 获取分组详情
- QPS 编辑保存调用 `PUT /api/groups/qps`

**设备列表组件 (GroupDeviceList.jsx)**
- 调用 `GET /api/groups/:groupName/devices` 获取设备列表
- 删除设备调用 `DELETE /api/groups/devices`
- 添加"移除可用队列"功能（后端需新增 API）

**Action 管理组件 (GroupAction.jsx)**
- 调用 `GET /api/groups/:groupName/actions` 获取 Action 列表
- 添加 Action 添加/删除功能（后端需新增 API）
- 添加监控图表展示（可选）

### 2. 后端功能增强

**新增 API 端点**
- `POST /api/groups/devices` - 添加设备到分组
- `PUT /api/groups/devices/disable` - 禁用/启用设备
- `POST /api/groups/actions` - 添加 Action
- `DELETE /api/groups/actions` - 删除 Action

**数据同步**
- 客户端注册/下线时同步更新 `group_device` 表
- 设备活跃度定时更新

### 3. 用户体验优化

- 添加加载状态提示
- 添加错误处理和重试机制
- 设备状态实时刷新（轮询或 WebSocket）
- 添加操作确认提示
- 添加表单验证

## 实现方案

### 方案 A：渐进式完善（推荐）

**优点：**
- 风险低，每次改动小
- 可快速验证功能
- 便于回滚

**缺点：**
- 需要多次迭代

**实施步骤：**
1. 修复现有 API 对接（列表、详情）
2. 实现创建/删除功能
3. 实现设备管理功能
4. 实现 Action 管理功能
5. 添加实时更新和优化

### 方案 B：一次性重构

**优点：**
- 一次性完成所有功能
- 代码风格统一

**缺点：**
- 风险较高
- 测试工作量大

## 推荐方案

采用**方案 A：渐进式完善**，按以下优先级实施：

1. **分组管理核心功能** - 创建、查看、删除、QPS 配置
2. **设备管理功能** - 真实数据对接、删除、状态刷新
3. **Action 管理功能** - 列表、添加、删除
4. **监控可视化** - 图表展示

**技术决策：**
- 设备状态更新：**轮询刷新**（每 5-10 秒）
- 创建/编辑交互：**Modal 对话框**

## 关键文件

### 后端文件
- `pkg/server/handlers/group.go` - 分组处理器
- `pkg/server/handlers/routes.go` - 路由配置
- `pkg/model/database.go` - 数据模型
- `pkg/database/database.go` - 数据库连接

### 前端文件
- `web/src/pages/GroupList.jsx` - 分组列表页面
- `web/src/pages/GroupDetail.jsx` - 分组详情页面
- `web/src/components/GroupDeviceList.jsx` - 设备列表组件
- `web/src/components/GroupAction.jsx` - Action 管理组件
- `web/src/utils/api.js` - API 工具
- `web/src/utils/index.js` - 工具函数

## 验证步骤

1. **后端 API 测试**
   ```bash
   # 获取分组列表
   curl http://localhost:5612/api/groups

   # 创建分组
   curl -X POST http://localhost:5612/api/groups \
     -H "Content-Type: application/json" \
     -d '{"groupName":"test","quotaQpsGroup":100}'

   # 获取分组详情
   curl http://localhost:5612/api/groups/test

   # 获取设备列表
   curl http://localhost:5612/api/groups/test/devices
   ```

2. **前端功能测试**
   - 启动前端：`cd web && npm run dev`
   - 访问分组管理页面
   - 测试创建、查看、删除分组
   - 测试设备管理
   - 测试 Action 管理

3. **端到端测试**
   - 启动服务器
   - 启动示例客户端
   - 验证设备状态实时更新

## 验收标准

- [ ] 分组 CRUD 功能完整
- [ ] 设备列表显示真实数据
- [ ] 设备删除功能可用
- [ ] Action 列表显示真实数据
- [ ] QPS 配置可保存
- [ ] 前端无模拟数据
- [ ] 错误处理完善
- [ ] 用户操作有明确反馈
