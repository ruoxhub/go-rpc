package api

import (
	"context"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/sekiro-go/sekiro-go/internal/utils/logger"
	"github.com/sekiro-go/sekiro-go/pkg/server/client"
)

// WebSocketHandler handles WebSocket connections
type WebSocketHandler struct {
	clientManager *client.ClientManager
}

// NewWebSocketHandler creates a new WebSocketHandler
func NewWebSocketHandler(manager *client.ClientManager) *WebSocketHandler {
	return &WebSocketHandler{
		clientManager: manager,
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

	// TODO: 实际的连接管理将在后续任务实现
	// 现在只是简单关闭连接
	wsConn.Close()

	c.Status(http.StatusOK)
}

// upgradeWebSocket performs the WebSocket upgrade
func (h *WebSocketHandler) upgradeWebSocket(w http.ResponseWriter, r *http.Request) (*websocket.Conn, error) {
	// 创建 WebSocket upgrader
	upgrader := &websocket.Upgrader{
		ReadBufferSize:  1024,
		WriteBufferSize: 1024,
		CheckOrigin: func(r *http.Request) bool {
			// 允许所有来源，生产环境应该根据实际需求配置
			return true
		},
	}

	// WebSocket 升级
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		return nil, err
	}

	return conn, nil
}

// HandleWebSocketUpgrade upgrades HTTP connection to WebSocket
func (h *WebSocketHandler) HandleWebSocketUpgrade(c *gin.Context, onConnect func(*websocket.Conn)) {
	group := c.Query("group")
	clientID := c.Query("clientId")

	if group == "" || clientID == "" {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "group and clientId parameters required",
		})
		return
	}

	logger.Infof("WebSocket register: group=%s, clientId=%s", group, clientID)

	conn, err := h.upgradeWebSocket(c.Writer, c.Request)
	if err != nil {
		logger.Errorf("WebSocket upgrade error: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "WebSocket upgrade failed",
		})
		return
	}

	logger.Infof("WebSocket upgrade successful: %s", c.ClientIP())

	// 启动连接处理器
	go func() {
		defer conn.Close()
		if onConnect != nil {
			onConnect(conn)
		}
		h.handleWebSocketConnection(context.Background(), conn, group, clientID)
	}()

	c.Status(http.StatusOK)
}

// handleWebSocketConnection handles the WebSocket connection
func (h *WebSocketHandler) handleWebSocketConnection(ctx context.Context, conn *websocket.Conn, group, clientID string) {
	// TODO: 实际的 WebSocket 消息处理将在后续任务实现
	for {
		select {
		case <-ctx.Done():
			return
		default:
			_, _, err := conn.ReadMessage()
			if err != nil {
				logger.Debugf("WebSocket connection closed: %v", err)
				return
			}
		}
	}
}

// IsWebSocketUpgrade checks if request is a WebSocket upgrade request
func IsWebSocketUpgrade(r *http.Request) bool {
	return r.Header.Get("Upgrade") == "websocket"
}
