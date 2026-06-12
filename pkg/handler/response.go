package handler

import (
	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/handler/errorcode"
	"github.com/mrh30000/go-rpc/pkg/utils/traceid"
)

// Response 是统一的 JSON 响应信封。所有 /api/*, /rpc-api/*, /business/* 端点共用该结构。
//
// 字段约定:
//   - Code:     业务错误码, 0 表示成功, 其余取值见 pkg/handler/errorcode。
//   - Message:  人类可读的成功 / 错误信息。
//   - Data:     成功时的业务数据; 失败时省略。
//   - Total:    分页总数, 仅分页查询使用, 0 时省略。
//   - TraceID:  由 TraceMiddleware 注入, 便于日志串联与排查, 缺失时省略。
//   - Group / ClientID: 仅 invoke 响应使用, 携带路由元数据, 便于前端定位客户端。
type Response struct {
	Code     int         `json:"code"`
	Message  string      `json:"message"`
	Data     interface{} `json:"data,omitempty"`
	Total    int64       `json:"total,omitempty"`
	TraceID  string      `json:"trace_id,omitempty"`
	Group    string      `json:"group,omitempty"`
	ClientID string      `json:"clientId,omitempty"`
}

// traceID 从 Gin 请求上下文读取 traceId; 缺失时返回空串, 序列化时由 omitempty 省略。
func traceID(c *gin.Context) string {
	if id, ok := traceid.FromContext(c.Request.Context()); ok {
		return id
	}
	return ""
}

// write 统一输出响应, 自动注入 trace_id。
func write(c *gin.Context, httpStatus int, r Response) {
	r.TraceID = traceID(c)
	c.JSON(httpStatus, r)
}

// OK 输出成功响应, code=0。
func OK(c *gin.Context, data interface{}) {
	write(c, 200, Response{Code: errorcode.Success, Message: "success", Data: data})
}

// OKWithTotal 输出分页成功响应。
func OKWithTotal(c *gin.Context, data interface{}, total int64) {
	write(c, 200, Response{Code: errorcode.Success, Message: "success", Data: data, Total: total})
}

// Fail 输出业务失败响应, HTTP 状态码由 errorcode.HTTPStatus(code) 决定。
func Fail(c *gin.Context, code int, message string) {
	write(c, errorcode.HTTPStatus(code), Response{Code: code, Message: message})
}

// FailWithRoute 输出带路由元数据的业务失败响应, 仅 invoke 路径使用。
func FailWithRoute(c *gin.Context, code int, message, group, clientID string) {
	r := Response{Code: code, Message: message, Group: group, ClientID: clientID}
	r.TraceID = traceID(c)
	c.JSON(errorcode.HTTPStatus(code), r)
}

// BadRequest 输出 1xxx 参数错误, HTTP 400。
func BadRequest(c *gin.Context, message string) {
	Fail(c, errorcode.BadRequest, message)
}

// Unauthorized 输出 2001 未认证, HTTP 401。
func Unauthorized(c *gin.Context, message string) {
	Fail(c, errorcode.Unauthorized, message)
}

// Forbidden 输出 2003 无权限, HTTP 403。
func Forbidden(c *gin.Context, message string) {
	Fail(c, errorcode.Forbidden, message)
}

// NotFound 输出 1004 资源不存在, HTTP 404。
func NotFound(c *gin.Context, message string) {
	Fail(c, errorcode.NotFound, message)
}

// InternalError 输出 5001 服务端错误, HTTP 500。
func InternalError(c *gin.Context, message string) {
	Fail(c, errorcode.InternalError, message)
}
