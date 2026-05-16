package handlers

import "github.com/gin-gonic/gin"

// ============================================================
// 管理 API 响应格式 (用于 /api/* 管理端点)
// 字段名: code / message / data / total
// ============================================================

// Response 管理 API 统一响应格式
type Response struct {
	Code    int         `json:"code"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
	Total   int64       `json:"total,omitempty"`
}

// Success 返回成功响应
func Success(c *gin.Context, data interface{}) {
	c.JSON(200, Response{
		Code:    0,
		Message: "success",
		Data:    data,
	})
}

// SuccessWithTotal 返回成功响应（带分页信息）
func SuccessWithTotal(c *gin.Context, data interface{}, total int64) {
	c.JSON(200, Response{
		Code:    0,
		Message: "success",
		Data:    data,
		Total:   total,
	})
}

// Error 返回错误响应
func Error(c *gin.Context, code int, message string) {
	c.JSON(code, Response{
		Code:    code,
		Message: message,
	})
}

// BadRequest 返回 400 错误
func BadRequest(c *gin.Context, message string) {
	Error(c, 400, message)
}

// Unauthorized 返回 401 错误
func Unauthorized(c *gin.Context, message string) {
	Error(c, 401, message)
}

// Forbidden 返回 403 错误
func Forbidden(c *gin.Context, message string) {
	Error(c, 403, message)
}

// NotFound 返回 404 错误
func NotFound(c *gin.Context, message string) {
	Error(c, 404, message)
}

// InternalError 返回 500 错误
func InternalError(c *gin.Context, message string) {
	Error(c, 500, message)
}

// ============================================================
// RPC API 响应格式 (用于 /rpc-api/* 前端兼容端点)
// 字段名: status / message / data
// 前端 Login.jsx 检查 response.data.status === 0
// ============================================================

// RpcApiResponse RPC API 响应格式
type RpcApiResponse struct {
	Status  int         `json:"status"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
}

// RpcApiSuccess 返回 RPC API 成功响应
func RpcApiSuccess(c *gin.Context, data interface{}) {
	c.JSON(200, RpcApiResponse{
		Status:  0,
		Message: "success",
		Data:    data,
	})
}

// RpcApiError 返回 RPC API 错误响应
func RpcApiError(c *gin.Context, status int, message string) {
	c.JSON(200, RpcApiResponse{
		Status:  status,
		Message: message,
	})
}

// RpcApiBadRequest 返回 RPC API 400 错误
func RpcApiBadRequest(c *gin.Context, message string) {
	RpcApiError(c, -1, message)
}

// RpcApiUnauthorized 返回 RPC API 401 错误
func RpcApiUnauthorized(c *gin.Context, message string) {
	RpcApiError(c, -1, message)
}

// RpcApiForbidden 返回 RPC API 403 错误
func RpcApiForbidden(c *gin.Context, message string) {
	RpcApiError(c, -1, message)
}

// RpcApiInternalError 返回 RPC API 500 错误
func RpcApiInternalError(c *gin.Context, message string) {
	RpcApiError(c, -1, message)
}
