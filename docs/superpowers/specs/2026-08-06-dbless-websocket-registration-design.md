# DB-less WebSocket 注册策略设计

## 背景

`RPC_DISABLE_DATABASE=true` 会跳过数据库、分组仓库和认证中间件的初始化。当前 `/business/register` 在 WebSocket 升级前执行分组访问检查，并在 `groupRepo` 或 `authMW` 缺失时返回 `503 Service Unavailable`。因此，虽然 DB-less 模式仍注册核心业务路由，RPC 客户端却无法建立 WebSocket 连接。

该行为来自安全加固：数据库模式下，认证依赖异常时必须 fail-closed。但它也把预期的 DB-less 运行模式误判成初始化故障。

## 目标

- DB-less 模式允许 RPC 客户端匿名注册并使用现有 `/business/*` 接口。
- 数据库模式保留现有分组、token 和所有权校验，不降低安全边界。
- 明确区分“配置选择 DB-less”与“数据库模式的鉴权依赖异常”。
- 用醒目的启动日志说明 DB-less 匿名开放风险。
- 采用完成目标所需的最小改动，不引入暂时不需要的鉴权机制。

## 非目标

本次不实现：

- DB-less 共享密钥或 token 鉴权。
- DB-less IP 白名单。
- 新的鉴权策略枚举或配置项。
- DB-less 限流或公网防护。
- 用户、分组或权限的内存持久化。
- 数据库模式鉴权规则变更。

## 运行模式与安全边界

### DB-less 模式

当 `RPC_DISABLE_DATABASE=true` 时：

- `/business/register` 允许任意客户端匿名注册。
- 其他 `/business/*` 接口沿用当前匿名访问行为。
- 不因 `groupRepo`、`authMW` 未初始化而返回 `503`。
- 启动时记录醒目的安全警告，说明业务接口未经鉴权，不应直接暴露到不可信网络。
- Web 管理、指标、告警及其他功能开关保持现有行为。

默认匿名开放是有意的兼容性选择。未来如需 DB-less 鉴权，应另行设计，不在本次改动中预留未使用的抽象或配置。

### 数据库模式

当 `RPC_DISABLE_DATABASE=false` 时：

- 注册请求继续执行全局 IP 白名单、分组查询、匿名访问配置、token 和用户所有权检查。
- `groupRepo` 或 `authMW` 异常缺失时继续 fail-closed，返回 `503`。
- 不根据依赖是否为空推断运行模式；运行模式以加载后的 `DisableDatabase` 配置为准。

## 组件与改动边界

实现保持在现有服务器组合根和注册授权流程内：

- `Server` 使用已加载的 `ServerConfig.DisableDatabase` 判断是否为 DB-less 模式。
- `authorizeRegisterAccess` 在执行数据库鉴权前处理明确的 DB-less 分支。
- 数据库模式的现有授权流程保持原样。
- DB-less 启动分支补充匿名开放安全警告。

不新增 authorizer 接口、Repository 实现或中间件。此次需求只有一种 DB-less 行为，引入策略抽象会增加没有当前消费者的复杂度。

## 请求流程

### DB-less WebSocket 注册

1. `/business/register` 校验 `group` 和 `clientId`。
2. 缺少参数时返回 `400 Bad Request`。
3. 注册授权读取明确的 `DisableDatabase` 配置。
4. DB-less 模式直接授权。
5. 服务执行 WebSocket Upgrade。
6. 升级成功后由现有 `wsHandler.HandleConnection` 管理连接。

### 数据库模式 WebSocket 注册

1. 校验 `group` 和 `clientId`。
2. 检查全局 IP 白名单。
3. 确认 `groupRepo` 和 `authMW` 可用；不可用时返回 `503`。
4. 查询分组配置。
5. 未注册分组按匿名访问配置处理。
6. 已注册分组校验 token 和用户所有权。
7. 授权成功后执行 WebSocket Upgrade。

## 错误语义

- DB-less 模式不再返回 `503 group access verification unavailable`。
- 缺少 `group` 或 `clientId` 仍返回 `400`。
- WebSocket Upgrade 失败继续记录服务端具体错误，并维持现有客户端表现。
- 数据库模式鉴权依赖异常仍返回 `503`。
- 数据库查询失败、无效 token 和越权访问继续使用现有错误状态及响应。

## 日志

DB-less 模式启动时应输出清晰且可检索的警告，至少表达：

- 数据库已禁用。
- `/business/*` 接口允许匿名访问。
- 该模式不应直接暴露到不可信网络。

日志不得包含凭证或其他敏感信息。

## 测试策略

新增或调整回归测试，覆盖：

- DB-less 模式下，有效 `group` 和 `clientId` 的注册请求通过授权阶段，不返回 `503`。
- DB-less 模式下缺少任一必需参数仍返回 `400`。
- 数据库模式下 `groupRepo` 或 `authMW` 缺失仍返回 `503`。
- 数据库模式已有的匿名分组、已注册分组 token 及所有权校验行为保持不变。
- 配置加载后的 `DisableDatabase` 值被注册授权流程明确使用。
- DB-less 启动时存在匿名开放警告；若当前日志设施无法稳定断言，则在验证记录中执行人工日志检查，不为此引入复杂测试设施。

## 验收标准

自动验证：

```powershell
rtk go test ./...
rtk go build ./...
```

手工验证：

1. 使用以下配置启动服务：

   ```dotenv
   RPC_DISABLE_WEB_ADMIN=true
   RPC_DISABLE_METRICS=true
   RPC_DISABLE_ALERT=true
   RPC_DISABLE_DATABASE=true
   ```

2. 确认启动日志包含 DB-less 匿名开放风险警告。
3. 确认 Kalodata Extractor 能连接 `/business/register`，不再持续出现 WebSocket `1006`。
4. 确认注册请求不再收到 `group access verification unavailable`。
5. 确认数据库模式的注册鉴权回归测试仍通过。

## 兼容性与风险

- 此设计恢复 DB-less 模式在安全加固前的匿名注册能力。
- DB-less 模式缺少身份和分组所有权保护；部署者必须通过网络边界隔离服务。
- 数据库模式继续 fail-closed，因此不会因本次兼容性修复扩大其授权范围。
- 未来增加 DB-less 鉴权时，应作为独立需求设计完整的配置、凭证传输和路由覆盖范围。
