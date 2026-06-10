package handler

import (
	"context"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	wsHandler "github.com/mrh30000/go-rpc/pkg/websocket"
)

// WebSocketHandler handles WebSocket connections
type WebSocketHandler struct {
	sekiroHandler *wsHandler.Handler
}

// NewWebSocketHandler creates a new WebSocketHandler
func NewWebSocketHandler(sekiroHandler *wsHandler.Handler) *WebSocketHandler {
	return &WebSocketHandler{
		sekiroHandler: sekiroHandler,
	}
}

// HandleRegister handles WebSocket registration requests
// GET /business/register?group=xxx&clientId=xxx
func (h *WebSocketHandler) HandleRegister(c *gin.Context) {
	// 获取查询参数
	group := c.Query("group")
	clientID := c.Query("clientId")

	if group == "" || clientID == "" {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "group and clientId parameters required",
		})
		return
	}

	logger.Infof("WebSocket register: group=%s, clientId=%s", group, clientID)

	// WebSocket 升级
	wsConn, err := h.upgradeWebSocket(c.Writer, c.Request)
	if err != nil {
		logger.Errorf("WebSocket upgrade error: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "WebSocket upgrade failed",
		})
		return
	}

	logger.Infof("WebSocket upgrade successful: %s", c.ClientIP())

	// 使用完整的 Rpc WebSocket 处理器处理连接
	ctx := context.Background()
	h.sekiroHandler.HandleConnection(ctx, wsConn, group, clientID)
}

// upgradeWebSocket performs the WebSocket upgrade
func (h *WebSocketHandler) upgradeWebSocket(w http.ResponseWriter, r *http.Request) (*websocket.Conn, error) {
	// 创建 WebSocket upgrader
	upgrader := &websocket.Upgrader{
		ReadBufferSize:  1024,
		WriteBufferSize: 1024,
		CheckOrigin:     sameOriginOrNoOrigin,
	}

	// WebSocket 升级
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		return nil, err
	}

	return conn, nil
}

// IsWebSocketUpgrade checks if request is a WebSocket upgrade request
func IsWebSocketUpgrade(r *http.Request) bool {
	return r.Header.Get("Upgrade") == "websocket"
}
