package handlers

import "github.com/gin-gonic/gin"

// Response 统一 API 响应格式
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
