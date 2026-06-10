package handler

import "github.com/gin-gonic/gin"

// ApiResponse is used by management API endpoints under /api/*.
type ApiResponse struct {
	Code    int         `json:"code"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
	Total   int64       `json:"total,omitempty"`
}

func Success(c *gin.Context, data interface{}) {
	c.JSON(200, ApiResponse{Code: 0, Message: "success", Data: data})
}

func SuccessWithTotal(c *gin.Context, data interface{}, total int64) {
	c.JSON(200, ApiResponse{Code: 0, Message: "success", Data: data, Total: total})
}

func Error(c *gin.Context, code int, message string) {
	c.JSON(code, ApiResponse{Code: code, Message: message})
}

func BadRequest(c *gin.Context, message string) {
	Error(c, 400, message)
}

func Unauthorized(c *gin.Context, message string) {
	Error(c, 401, message)
}

func Forbidden(c *gin.Context, message string) {
	Error(c, 403, message)
}

func NotFound(c *gin.Context, message string) {
	Error(c, 404, message)
}

func InternalError(c *gin.Context, message string) {
	Error(c, 500, message)
}

// RpcResponse is used by external RPC endpoints under /rpc-api/* and /business/*.
type RpcResponse struct {
	Status  int         `json:"status"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
}

func RpcSuccess(c *gin.Context, data interface{}) {
	c.JSON(200, RpcResponse{Status: 0, Message: "success", Data: data})
}

func RpcError(c *gin.Context, status int, message string) {
	c.JSON(200, RpcResponse{Status: status, Message: message})
}

func RpcServerError(c *gin.Context, message string) {
	c.JSON(500, RpcResponse{Status: -1, Message: message})
}

func RpcUnauthorized(c *gin.Context, message string) {
	c.JSON(401, RpcResponse{Status: -1, Message: message})
}

func RpcForbidden(c *gin.Context, message string) {
	c.JSON(403, RpcResponse{Status: -1, Message: message})
}

// RpcExtraResponse is used by RPC responses that include routing metadata.
type RpcExtraResponse struct {
	Status   int         `json:"status"`
	Message  string      `json:"message"`
	Group    string      `json:"group,omitempty"`
	ClientID string      `json:"clientId,omitempty"`
	Data     interface{} `json:"data,omitempty"`
}
