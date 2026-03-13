package api

import (
	"context"
	"net/http"

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
func (h *WebSocketHandler) HandleRegister(w http.ResponseWriter, r *http.Request) {
	// 获取查询参数
	group := r.URL.Query().Get("group")
	clientID := r.URL.Query().Get("clientId")

	if group == "" || clientID == "" {
		http.Error(w, "group and clientId parameters required", http.StatusBadRequest)
		return
	}

	logger.Infof("WebSocket register: group=%s, clientId=%s", group, clientID)

	// WebSocket 升级
	wsConn, err := h.upgradeWebSocket(w, r)
	if err != nil {
		logger.Errorf("WebSocket upgrade error: %v", err)
		return
	}

	logger.Infof("WebSocket upgrade successful: %s", r.RemoteAddr)

	// TODO: 实际的连接管理将在后续任务实现
	// 现在只是简单关闭连接
	wsConn.Close()
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
func (h *WebSocketHandler) HandleWebSocketUpgrade(w http.ResponseWriter, r *http.Request, onConnect func(*websocket.Conn)) {
	group := r.URL.Query().Get("group")
	clientID := r.URL.Query().Get("clientId")

	if group == "" || clientID == "" {
		http.Error(w, "group and clientId parameters required", http.StatusBadRequest)
		return
	}

	logger.Infof("WebSocket register: group=%s, clientId=%s", group, clientID)

	conn, err := h.upgradeWebSocket(w, r)
	if err != nil {
		logger.Errorf("WebSocket upgrade error: %v", err)
		return
	}

	logger.Infof("WebSocket upgrade successful: %s", r.RemoteAddr)

	// 启动连接处理器
	go func() {
		defer conn.Close()
		if onConnect != nil {
			onConnect(conn)
		}
		h.handleWebSocketConnection(context.Background(), conn, group, clientID)
	}()
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
