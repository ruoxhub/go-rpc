package api

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

// ============================================================
// 业务 API 响应格式 (用于 /business/* 业务端点)
// 字段名: status / message / data
// 与外部调用端 / 前端 SDK 兼容，必须使用 status 字段
// ============================================================

// BusinessResponse 业务 API 统一响应格式
type BusinessResponse struct {
	Status  int         `json:"status"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
}

// BusinessExtraResponse 业务 API 响应格式（带额外字段，用于 RPC 调用响应）
type BusinessExtraResponse struct {
	Status   int         `json:"status"`
	Message  string      `json:"message"`
	Group    string      `json:"group,omitempty"`
	ClientID string      `json:"clientId,omitempty"`
	Data     interface{} `json:"data,omitempty"`
}

// BusinessSuccess 返回业务 API 成功响应
func BusinessSuccess(c *gin.Context, data interface{}) {
	c.JSON(http.StatusOK, BusinessResponse{
		Status:  0,
		Message: "success",
		Data:    data,
	})
}

// BusinessError 返回业务 API 错误响应
func BusinessError(c *gin.Context, message string) {
	c.JSON(http.StatusOK, BusinessResponse{
		Status:  -1,
		Message: message,
	})
}

// BusinessServerError 返回业务 API 服务器错误响应
func BusinessServerError(c *gin.Context, message string) {
	c.JSON(http.StatusInternalServerError, BusinessResponse{
		Status:  -1,
		Message: message,
	})
}

// BusinessUnauthorized 返回业务 API 未授权响应
func BusinessUnauthorized(c *gin.Context, message string) {
	c.JSON(http.StatusUnauthorized, BusinessResponse{
		Status:  -1,
		Message: message,
	})
}

// BusinessForbidden 返回业务 API 禁止访问响应
func BusinessForbidden(c *gin.Context, message string) {
	c.JSON(http.StatusForbidden, BusinessResponse{
		Status:  -1,
		Message: message,
	})
}
