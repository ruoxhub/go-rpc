# Sekiro RPC Server — 业务错误码对照表

> 自本次重构起, 所有 `/api/*`、`/rpc-api/*`、`/business/*` 端点的 JSON 响应共用统一信封,
> `code` 字段为业务错误码, 与 HTTP 状态码解耦。

## 统一响应信封

```json
{
  "code":     0,             // 业务错误码, 0 表示成功
  "message":  "success",     // 人类可读文案
  "data":     { ... },       // 成功时的业务数据, 失败时省略
  "total":    100,           // 仅分页查询, 0 时省略
  "trace_id": "abc123...",   // 由 TraceMiddleware 注入, 缺失时省略
  "group":    "g1",          // 仅 invoke 响应, 路由元数据
  "clientId": "c1"           // 仅 invoke 响应, 路由元数据
}
```

HTTP 状态码仅表达传输层语义 (200/400/401/403/404/500), 业务成败与错误类别一律由 `code` 表达。

## 错误码分段

| 段      | 含义             |
|---------|------------------|
| `0`     | 成功             |
| `1xxx`  | 参数 / 请求错误  |
| `2xxx`  | 认证 / 授权错误  |
| `3xxx`  | 业务逻辑错误     |
| `5xxx`  | 服务端内部错误   |

## 完整对照表

| Code | 常量                      | 默认文案                  | HTTP | 触发场景                                       |
|------|---------------------------|---------------------------|------|------------------------------------------------|
| 0    | `Success`                 | success                   | 200  | 成功                                           |
| 1000 | `BadRequest`              | bad request               | 400  | 通用参数错误                                   |
| 1001 | `InvalidParams`           | invalid parameters        | 200  | 具体参数缺失 / 格式错误 (如 invoke 请求构建失败) |
| 1004 | `NotFound`                | not found                 | 404  | 资源 (用户 / 规则 / 设备) 不存在               |
| 2001 | `Unauthorized`            | unauthorized              | 401  | 未登录或 token 无效                            |
| 2002 | `TokenExpired`            | token expired             | 401  | token 过期 (预留, 暂未启用)                    |
| 2003 | `Forbidden`               | forbidden                 | 403  | 无权限访问该资源 / 分组                        |
| 2004 | `RegisterDisabled`        | registration disabled     | 403  | 系统禁止新用户注册                             |
| 3001 | `NoClientAvailable`       | no client available       | 200  | invoke 路由不到可用客户端                      |
| 3002 | `GroupAccessDenied`       | group access denied       | 200  | 当前用户无权限访问该分组                       |
| 3003 | `ActionNotFound`          | action not found          | 200  | 请求的 action 不存在                           |
| 3004 | `ClientInvokeFailed`      | client invoke failed      | 200  | RPC 客户端返回业务错误 (客户端 status=0 时降级) |
| 3005 | `EmptyInvoke`             | empty invoke rejected     | 200  | 空转调用被拒绝 (DefendIdleInvoke 开关命中)     |
| 3006 | `Timeout`                 | request timeout           | 200  | 等待客户端响应超时                             |
| 5001 | `InternalError`           | internal server error     | 500  | 通用服务端错误                                 |
| 5002 | `DatabaseError`           | database error            | 500  | 数据库异常                                     |
| 5003 | `MarshalFailed`           | marshal failed            | 500  | JSON / 协议序列化失败                          |
| 5004 | `EncryptFailed`           | encrypt failed            | 500  | 密码等加密失败                                 |
| 5005 | `RepositoryInit`          | repository not initialized| 500  | Repository 未初始化                            |

## 前端消费建议

```javascript
// axios 响应拦截器 (详见 web/src/utils/api.js)
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const body = error.response?.data
    // 服务端业务错误: HTTP 2xx 但 code !== 0, 或 HTTP 4xx/5xx
    if (body?.code && body.code !== 0) {
      message.error(body.message || '请求失败')
    }
    return Promise.reject(error)
  }
)

// 页面代码显式判断成功
if (response.code === 0) {
  // 使用 response.data
}
```

## 迁移说明

本次统一信封前, `/api/*` 使用 `code`, `/rpc-api/*` 与 `/business/*` 使用 `status` (成功 0, 失败 -1)。
迁移后:
- 所有路径统一使用 `code` (旧字段 `status` 删除)
- 旧的 `-1` 通用错误码按语义映射为上表中的具体错误码
- 前端原 `response.data.status === 0` 判断改为 `response.data.code === 0`
- invoke 响应仍保留 "客户端返回 JSON 时平级展开到顶层" 行为 (SDK 兼容)

## SDK 字段名对照

| 语言 / 包                                  | 解析字段        | 备注                                       |
|--------------------------------------------|-----------------|--------------------------------------------|
| Go `pkg/client/sdk` (`InvokeResponse`)     | `Code int`      | JSON tag `"code"`, 与服务端对齐            |
| Go `sample/go/sekio` (`commonRes`)         | `Status int32`  | JSON tag `"code"`, 二进制协议字段名不变    |
| Python `sample/python/Invoker.py`          | dict key `code` | 旧版本使用 `status`, 升级时需同步替换     |

## 相关源码

- 错误码常量与工具函数: `pkg/handler/errorcode/errorcode.go`
- 响应信封与辅助函数: `pkg/handler/response.go`
- Invoke 响应渲染: `pkg/handler/invoke.go` (`renderUnaryResponse` / `writeForwardError`)
