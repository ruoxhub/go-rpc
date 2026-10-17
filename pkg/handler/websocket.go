package handler

import (
	"context"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/mrh30000/go-rpc/pkg/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/protocol"
	wsHandler "github.com/mrh30000/go-rpc/pkg/websocket"
)

// RegisterAuthorizer validates whether a client may register into a group
// before the WebSocket upgrade. Return false after writing the HTTP error.
type RegisterAuthorizer func(c *gin.Context, group string) bool

// WebSocketHandler handles WebSocket connections
type WebSocketHandler struct {
	sekiroHandler *wsHandler.Handler
	authorize     RegisterAuthorizer
}

// NewWebSocketHandler creates a new WebSocketHandler.
// authorize may be nil only in tests that do not exercise auth; production
// must pass the same authorizeRegisterAccess used by main.handleRegister.
func NewWebSocketHandler(sekiroHandler *wsHandler.Handler, authorize RegisterAuthorizer) *WebSocketHandler {
	return &WebSocketHandler{
		sekiroHandler: sekiroHandler,
		authorize:     authorize,
	}
}

// HandleRegister handles WebSocket registration requests
// GET /business/register?group=xxx&clientId=xxx
func (h *WebSocketHandler) HandleRegister(c *gin.Context) {
	group := c.Query("group")
	clientID := c.Query("clientId")

	if group == "" || clientID == "" {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "group and clientId parameters required",
		})
		return
	}

	// Always run group access checks before upgrading the connection.
	// Without an authorizer, fail closed to avoid unauthenticated register.
	if h.authorize == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"error": "register authorization not configured",
		})
		return
	}
	if !h.authorize(c, group) {
		return
	}

	logger.Debugf("WebSocket register: group=%s, clientId=%s", group, clientID)

	wsConn, err := h.upgradeWebSocket(c.Writer, c.Request)
	if err != nil {
		logger.Errorf("WebSocket upgrade error: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "WebSocket upgrade failed",
		})
		return
	}

	logger.Debugf("WebSocket upgrade successful: %s", c.ClientIP())

	executorType := strings.TrimSpace(c.Query("executor_type"))
	reg := protocol.LegacyRegistration()
	reg.ExecutorType = executorType

	ctx := context.Background()
	h.sekiroHandler.HandleConnectionWithRegistration(ctx, wsConn, group, clientID, reg)
}

// upgradeWebSocket performs the WebSocket upgrade
func (h *WebSocketHandler) upgradeWebSocket(w http.ResponseWriter, r *http.Request) (*websocket.Conn, error) {
	// 创建 WebSocket upgrader
	upgrader := &websocket.Upgrader{
		ReadBufferSize:  1024,
		WriteBufferSize: 1024,
		CheckOrigin: func(r *http.Request) bool {
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

// IsWebSocketUpgrade checks if request is a WebSocket upgrade request
func IsWebSocketUpgrade(r *http.Request) bool {
	return r.Header.Get("Upgrade") == "websocket"
}
