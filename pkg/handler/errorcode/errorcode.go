// Package errorcode 定义统一的业务错误码。
//
// 分段规则:
//   - 0       : 成功
//   - 1xxx    : 参数 / 请求错误
//   - 2xxx    : 认证 / 授权错误
//   - 3xxx    : 业务逻辑错误 (客户端路由、分组权限、action 等)
//   - 5xxx    : 服务端内部错误
//
// 错误码是 JSON 响应 "code" 字段的取值, 与 HTTP 状态码解耦: HTTP 状态码仅表达传输层语义
// (200/400/401/403/404/500), 业务成败与错误类别一律由 code 表达。
package errorcode

// 成功
const Success = 0

// 1xxx 参数 / 请求错误
const (
	BadRequest    = 1000 // 通用参数错误
	InvalidParams = 1001 // 具体参数缺失 / 格式错误
	NotFound      = 1004 // 资源不存在
)

// 2xxx 认证 / 授权错误
const (
	Unauthorized     = 2001 // 未登录或 token 无效
	TokenExpired     = 2002 // token 过期
	Forbidden        = 2003 // 无权限访问该资源
	RegisterDisabled = 2004 // 系统禁止新用户注册
)

// 3xxx 业务逻辑错误
const (
	NoClientAvailable  = 3001 // invoke 时路由不到可用客户端
	GroupAccessDenied  = 3002 // 当前用户无权限访问该分组
	ActionNotFound     = 3003 // 请求的 action 不存在
	ClientInvokeFailed = 3004 // RPC 客户端返回业务错误
	EmptyInvoke        = 3005 // 空转调用被拒绝 (管理员未配置处理逻辑)
	Timeout            = 3006 // 等待客户端响应超时
)

// 5xxx 服务端内部错误
const (
	InternalError  = 5001 // 通用服务端错误
	DatabaseError  = 5002 // 数据库异常
	MarshalFailed  = 5003 // 序列化失败
	EncryptFailed  = 5004 // 密码等加密失败
	RepositoryInit = 5005 // Repository 未初始化
)

// messages 错误码到默认文案的映射。仅供日志与兜底提示使用, 业务代码应提供具体中文 / 英文信息。
var messages = map[int]string{
	Success:            "success",
	BadRequest:         "bad request",
	InvalidParams:      "invalid parameters",
	NotFound:           "not found",
	Unauthorized:       "unauthorized",
	TokenExpired:       "token expired",
	Forbidden:          "forbidden",
	RegisterDisabled:   "registration disabled",
	NoClientAvailable:  "no client available",
	GroupAccessDenied:  "group access denied",
	ActionNotFound:     "action not found",
	ClientInvokeFailed: "client invoke failed",
	EmptyInvoke:        "empty invoke rejected",
	Timeout:            "request timeout",
	InternalError:      "internal server error",
	DatabaseError:      "database error",
	MarshalFailed:      "marshal failed",
	EncryptFailed:      "encrypt failed",
	RepositoryInit:     "repository not initialized",
}

// Message 返回错误码的默认英文文案; 未知错误码返回 "unknown error"。
func Message(code int) string {
	if msg, ok := messages[code]; ok {
		return msg
	}
	return "unknown error"
}

// HTTPStatus 把业务错误码映射为合适的 HTTP 状态码, 用于辅助函数自动设置响应 status。
//
//	1xxx → 400
//	2001/2002 → 401
//	2003/2004 → 403
//	1004 → 404
//	其它 → 500
func HTTPStatus(code int) int {
	switch {
	case code == Success:
		return 200
	case code == NotFound:
		return 404
	case code == Unauthorized || code == TokenExpired:
		return 401
	case code == Forbidden || code == RegisterDisabled:
		return 403
	case code >= 1000 && code < 2000:
		return 400
	case code >= 5000:
		return 500
	default:
		// 3xxx 业务错误传输层仍返回 200, 与 RPC 协议传统一致 (业务失败由 code 表达)。
		return 200
	}
}
