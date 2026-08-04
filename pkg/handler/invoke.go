package handler

import (
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	json "github.com/goccy/go-json"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/client"
	"github.com/mrh30000/go-rpc/pkg/config"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/eventbus"
	"github.com/mrh30000/go-rpc/pkg/forwarder"
	"github.com/mrh30000/go-rpc/pkg/handler/errorcode"
	"github.com/mrh30000/go-rpc/pkg/metrics"
	"github.com/mrh30000/go-rpc/pkg/middleware"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/router"
	ws "github.com/mrh30000/go-rpc/pkg/websocket"
)

// APIHandler handles HTTP API requests
type APIHandler struct {
	clientManager    clientManagerIface
	router           *router.Router
	wsHandler        *ws.Handler
	timeoutManager   *forwarder.TimeoutManager
	metricsCollector metrics.MetricCollector
	configService    config.Service
	groupRepo        repository.GroupRepository
	eventBus         *eventbus.EventBus
	authMW           *middleware.AuthMiddleware
}

// clientManagerIface is the interface for client manager (internal)
type clientManagerIface interface {
	GetAllGroups() []string
	GetClientsByGroup(group string) []*client.RpcClient
	AllocateClient(group string) *client.RpcClient
	GetClient(group, clientID string) *client.RpcClient
	GetGroup(groupName string) *client.RpcGroup
}

// RequestBuilder defines the interface for building request data.
//
// 注意：原 GetAccessToken() 已删除。鉴权由中间件 (middleware.AuthMiddleware /
// OptionalAuth) 负责从 Authorization / sekiro-token header 解析用户并写入
// gin.Context，业务层用 middleware.GetCurrentUser 取即可。
type RequestBuilder interface {
	BuildRequestData() (action string, params interface{}, err error)
	GetTimeout() time.Duration
	GetSequence(group string) string
	ShouldRecordMetrics() bool
	GetMetricAPI(action string) string
	GetGroup() string
	GetClientID() string
	GetConstantInvoke() string
	IsStream() bool
	IsFuzzy() bool
}

// InvokeRequest represents the invoke request body
type InvokeRequest struct {
	Group          string      `json:"group"`
	ClientID       string      `json:"clientId,omitempty"`
	ConstantInvoke string      `json:"constantInvoke,omitempty"`
	Timeout        int         `json:"timeout,omitempty"`
	Action         string      `json:"action"`
	Params         interface{} `json:"params,omitempty"`
	Stream         bool        `json:"stream,omitempty"`
	Fuzzy          bool        `json:"fuzzy,omitempty"`
}

// NewAPIHandler creates a new APIHandler
func NewAPIHandler(manager *client.ClientManager, wsHandler *ws.Handler, timeoutMgr *forwarder.TimeoutManager, metricsCollector metrics.MetricCollector, cfgSvc config.Service, eventBus *eventbus.EventBus, groupRepo repository.GroupRepository, authMW *middleware.AuthMiddleware) *APIHandler {
	h := &APIHandler{
		clientManager:    manager,
		router:           router.NewRouter(cfgSvc),
		wsHandler:        wsHandler,
		timeoutManager:   timeoutMgr,
		metricsCollector: metricsCollector,
		configService:    cfgSvc,
		groupRepo:        groupRepo,
		eventBus:         eventBus,
		authMW:           authMW,
	}

	if eventBus != nil {
		eventbus.SubscribeTyped(eventBus, eventbus.EventClientConnect, func(e eventbus.ClientConnectEvent) {
			h.router.InvalidateRingCache(e.Group)
		})
		eventbus.SubscribeTyped(eventBus, eventbus.EventClientDisconnect, func(e eventbus.ClientDisconnectEvent) {
			h.router.InvalidateRingCache(e.Group)
		})
	}

	return h
}

// HandleGroupList handles /business/groupList request
// GET /business/groupList
func (h *APIHandler) HandleGroupList(c *gin.Context) {
	groups := h.clientManager.GetAllGroups()
	logger.Debugf("HandleGroupList: raw groups=%v, count=%d", groups, len(groups))
	filtered, err := h.filterAccessibleGroups(c, groups)
	if err != nil {
		InternalError(c, err.Error())
		return
	}
	logger.Debugf("HandleGroupList: filtered groups=%v, count=%d", filtered, len(filtered))
	OK(c, filtered)
}

// HandleClientQueue handles /business/clientQueue request
// GET /business/clientQueue?group=xxx
func (h *APIHandler) HandleClientQueue(c *gin.Context) {
	group := c.Query("group")
	if group == "" {
		BadRequest(c, "group parameter required")
		return
	}
	if !h.authorizeRegisteredGroupAccess(c, group) {
		return
	}

	clients := h.clientManager.GetClientsByGroup(group)
	clientIDs := make([]string, len(clients))
	for i, c := range clients {
		clientIDs[i] = c.ClientID
	}

	OK(c, clientIDs)
}

// HandleKickClient handles DELETE /business/kick
//
// Query 参数:
//   - group (required): 目标分组
//   - clientId (optional): 目标客户端；为空时踢除整个分组的所有客户端
func (h *APIHandler) HandleKickClient(c *gin.Context) {
	groupName := c.Query("group")
	if groupName == "" {
		BadRequest(c, "group parameter required")
		return
	}
	if !h.authorizeRegisteredGroupAccess(c, groupName) {
		return
	}

	rpcGroup := h.clientManager.GetGroup(groupName)
	if rpcGroup == nil {
		NotFound(c, "group not found")
		return
	}

	clientID := c.Query("clientId")
	if clientID == "" {
		// 整组踢除：逐个 Unregister，避免 Close() 销毁 group goroutine
		for _, cl := range rpcGroup.GetAllClients() {
			rpcGroup.Unregister(cl.ClientID)
			if h.eventBus != nil {
				eventbus.PublishTyped(h.eventBus, eventbus.EventClientKicked, eventbus.ClientKickedEvent{
					Group:     groupName,
					ClientID:  cl.ClientID,
					Timestamp: time.Now(),
				})
			}
		}
		OK(c, "all clients kicked from group")
		return
	}

	if !rpcGroup.HasClient(clientID) {
		NotFound(c, "client not found")
		return
	}

	rpcGroup.Unregister(clientID)

	if h.eventBus != nil {
		eventbus.PublishTyped(h.eventBus, eventbus.EventClientKicked, eventbus.ClientKickedEvent{
			Group:     groupName,
			ClientID:  clientID,
			Timestamp: time.Now(),
		})
	}

	OK(c, "client kicked")
}

// HandleInvoke handles /business/invoke request
// POST/GET /business/invoke
func (h *APIHandler) HandleInvoke(c *gin.Context) {
	startTime := time.Now()
	req := bindInvokeRequest(c)

	// 参数验证
	if req.Action == "" {
		BadRequest(c, "action parameter required")
		return
	}

	builder := newInvokeBuilder(&req)
	h.handleForwardRequest(c, builder, startTime)
}

// bindInvokeRequest 解析 /business/invoke 的输入:
// POST 优先尝试 JSON 绑定, 失败时回退到 query 参数; GET 走 query。
// 鉴权信息 (sekiro_token) 不再从此 body/query 读取，统一由 AuthMiddleware 从
// Authorization / sekiro-token 头解析并写入 context。
func bindInvokeRequest(c *gin.Context) InvokeRequest {
	var req InvokeRequest

	if c.Request.Method == http.MethodPost {
		if err := c.ShouldBindJSON(&req); err != nil {
			req = invokeRequestFromQuery(c)
		}
	} else {
		req = invokeRequestFromQuery(c)
	}

	// query 中的 stream 优先级更低，但 body 没显式设置时仍然让它生效
	if !req.Stream {
		if v := c.Query("stream"); v != "" {
			req.Stream = parseBoolQuery(v)
		}
	}
	if !req.Fuzzy {
		if v := c.Query("fuzzy"); v != "" {
			req.Fuzzy = parseBoolQuery(v)
		}
	}
	return req
}

func invokeRequestFromQuery(c *gin.Context) InvokeRequest {
	return InvokeRequest{
		Group:          c.Query("group"),
		ClientID:       c.Query("clientId"),
		ConstantInvoke: c.Query("constantInvoke"),
		Action:         c.Query("action"),
		Stream:         parseBoolQuery(c.Query("stream")),
		Fuzzy:          parseBoolQuery(c.Query("fuzzy")),
	}
}

// parseBoolQuery 把 query 中的 stream 字符串转 bool（"1"/"true"/"yes"/"on"）
func parseBoolQuery(v string) bool {
	switch strings.ToLower(strings.TrimSpace(v)) {
	case "1", "true", "yes", "on":
		return true
	}
	return false
}

func (h *APIHandler) selectTargetClient(groupName, clientID string, fuzzy bool, constantInvoke, action string, payload interface{}, requestTraceID string) (*client.RpcClient, error) {
	group := h.clientManager.GetGroup(groupName)
	if group == nil {
		if clientID != "" {
			return nil, fmt.Errorf("group %s not found", groupName)
		}
		return nil, nil
	}

	params := router.RouteParams{GroupName: groupName, ClientID: clientID, Fuzzy: fuzzy}
	if clientID == "" {
		params.ConstantInvoke = constantInvoke
		params.Action = action
		params.Payload = payload
	}

	selected := h.router.Route(group, params)
	if selected == nil {
		if clientID != "" {
			return nil, fmt.Errorf("client %s not found in group %s", clientID, groupName)
		}
		return nil, nil
	}

	requestLogger := logger.WithTraceID(requestTraceID)
	if clientID != "" {
		requestLogger.Debugf("Route selected: strategy=specified, group=%s, clientId=%s, fuzzy=%v", groupName, selected.ClientID, fuzzy)
	} else {
		requestLogger.Debugf("Route selected: group=%s, clientId=%s", groupName, selected.ClientID)
	}
	return selected, nil
}

// ==================== Request Builder Implementations ====================

// maxInvokeTimeout is the maximum allowed timeout for invoke requests
const maxInvokeTimeout = 5 * time.Minute

// InvokeBuilder handles standard invoke requests
type InvokeBuilder struct {
	Group          string
	ClientID       string
	ConstantInvoke string
	Action         string
	Params         interface{}
	Timeout        time.Duration
	Stream         bool
	Fuzzy          bool
}

func newInvokeBuilder(req *InvokeRequest) *InvokeBuilder {
	return &InvokeBuilder{
		Group:          req.Group,
		ClientID:       req.ClientID,
		ConstantInvoke: req.ConstantInvoke,
		Action:         req.Action,
		Params:         req.Params,
		Timeout:        time.Duration(req.Timeout) * time.Second,
		Stream:         req.Stream,
		Fuzzy:          req.Fuzzy,
	}
}

func (b *InvokeBuilder) BuildRequestData() (string, interface{}, error) {
	return b.Action, b.Params, nil
}

func (b *InvokeBuilder) GetTimeout() time.Duration {
	if b.Timeout <= 0 {
		return 30 * time.Second
	}
	if b.Timeout > maxInvokeTimeout {
		return maxInvokeTimeout
	}
	return b.Timeout
}

func (b *InvokeBuilder) GetSequence(group string) string {
	return fmt.Sprintf("%s-%s-%d", group, b.Action, time.Now().UnixNano())
}

func (b *InvokeBuilder) ShouldRecordMetrics() bool {
	return true
}

func (b *InvokeBuilder) GetMetricAPI(action string) string {
	return b.Action
}

func (b *InvokeBuilder) GetGroup() string          { return b.Group }
func (b *InvokeBuilder) GetClientID() string       { return b.ClientID }
func (b *InvokeBuilder) GetConstantInvoke() string { return b.ConstantInvoke }
func (b *InvokeBuilder) IsStream() bool            { return b.Stream }
func (b *InvokeBuilder) IsFuzzy() bool             { return b.Fuzzy }

// handleForwardRequest 把 RequestBuilder 描述的请求转发到 Rpc 客户端。
//
// 流程: 校验 -> 鉴权 -> 空转保护 -> 选客户端 -> 构包 -> 分发到 stream / unary 子流程。
// 每段拆出独立 helper, 让本函数只承担"编排"职责。
func (h *APIHandler) handleForwardRequest(c *gin.Context, builder RequestBuilder, startTime time.Time) {
	group := builder.GetGroup()
	clientID := builder.GetClientID()
	constantInvoke := builder.GetConstantInvoke()

	reqAction, reqParams, buildErr := builder.BuildRequestData()
	requestTraceID := traceID(c)
	requestLogger := logger.WithTraceID(requestTraceID)
	requestLogger.Debugf("Request: group=%s, clientId=%s, action=%s", group, clientID, reqAction)

	if group == "" {
		BadRequest(c, "group parameter required")
		return
	}
	if !h.authorizeRegisteredGroupAccess(c, group) {
		return
	}
	if h.rejectIdleInvoke(builder, constantInvoke) {
		logger.Warnf("DefendIdleInvoke: blocked constant invoke request, group=%s, action=%s", group, reqAction)
		Fail(c, errorcode.EmptyInvoke, "空转调用被拒绝，请联系管理员配置实际处理逻辑")
		return
	}
	// BuildRequestData 的错误延迟到鉴权 / 空转保护之后再返回, 与重构前的语义保持一致
	// (老代码原本就是先 idle-defense 再 BuildRequestData)。
	if buildErr != nil {
		Fail(c, errorcode.InvalidParams, "Failed to build request data: "+buildErr.Error())
		return
	}

	targetClient, err := h.selectTargetClient(group, clientID, builder.IsFuzzy(), constantInvoke, reqAction, reqParams, requestTraceID)
	if err != nil {
		Fail(c, errorcode.NoClientAvailable, err.Error())
		return
	}
	if targetClient == nil {
		Fail(c, errorcode.NoClientAvailable, "no client available")
		return
	}

	reqDataJSON, err := json.Marshal(map[string]interface{}{
		"action": reqAction,
		"params": reqParams,
	})
	if err != nil {
		Fail(c, errorcode.MarshalFailed, "Failed to marshal request data: "+err.Error())
		return
	}

	sequence := builder.GetSequence(group)
	timeout := builder.GetTimeout()

	if builder.IsStream() {
		h.forwardStream(c, builder, group, targetClient, sequence, reqDataJSON, timeout, startTime, reqAction)
		return
	}
	h.forwardUnary(c, builder, group, targetClient, sequence, reqDataJSON, timeout, startTime, reqAction)
}

// rejectIdleInvoke 是 invoke 端的"空转调用保护": 仅 invoke 类 builder 启用,
// 当 ConfigKeyDefendIdleInvoke 开启 + 请求显式打了 constantInvoke=true/1 时拒绝放行。
func (h *APIHandler) rejectIdleInvoke(builder RequestBuilder, constantInvoke string) bool {
	if !builder.ShouldRecordMetrics() {
		return false
	}
	if h.configService == nil || !h.configService.GetConfigBool(config.ConfigKeyDefendIdleInvoke, true) {
		return false
	}
	return constantInvoke == "true" || constantInvoke == "1"
}

// forwardStream 走流式分支: 注册 StreamRecord -> 发起 invoke -> SSE chunked 输出。
// 发送失败时 RemoveStream 并以 -1 错误响应回包 (HTTP 头还没发出, 安全)。
func (h *APIHandler) forwardStream(c *gin.Context, builder RequestBuilder, group string,
	targetClient *client.RpcClient, sequence string, reqDataJSON []byte,
	timeout time.Duration, startTime time.Time, reqAction string) {

	requestTraceID := traceID(c)
	streamRec := h.timeoutManager.RegisterStream(sequence, group, targetClient.ClientID, timeout)
	streamRec.TraceID = requestTraceID

	if err := h.wsHandler.SendInvokeRequest(targetClient, sequence, group, targetClient.ClientID, reqDataJSON, requestTraceID); err != nil {
		h.timeoutManager.RemoveStream(sequence)
		targetClient.MarkFailure()
		h.writeForwardError(c, group, targetClient.ClientID, fmt.Errorf("Failed to send request: %w", err))
		return
	}
	logger.WithTraceID(requestTraceID).Debugf("Stream request sent: sequence=%s, group=%s, clientId=%s", sequence, group, targetClient.ClientID)
	h.streamSSEResponse(c, streamRec, group, targetClient, builder, startTime, reqAction)
}

// forwardUnary 走 unary 分支: Add 记录 -> 发起 invoke -> 阻塞等响应 / 超时, 然后渲染。
func (h *APIHandler) forwardUnary(c *gin.Context, builder RequestBuilder, group string,
	targetClient *client.RpcClient, sequence string, reqDataJSON []byte,
	timeout time.Duration, startTime time.Time, reqAction string) {

	resp, ok := h.dispatchInvokeRequest(c, group, targetClient, sequence, reqDataJSON, timeout, traceID(c))
	if !ok {
		return
	}
	if resp == nil {
		// ctx 超时分支已写过响应包络并记录了 metric
		h.recordInvokeMetric(builder, group, reqAction, "timeout", startTime)
		return
	}
	h.renderUnaryResponse(c, builder, group, targetClient, resp, reqAction, startTime)
}

// dispatchInvokeRequest 统一处理 "Add + send + wait" 三步:
//   - 发送失败时 Remove + MarkFailure + 写错误包络, 返回 (nil, false)
//   - ctx 超时分支: Remove + MarkFailure + 写错误包络, 返回 (nil, true) (调用者仍可补埋点)
//   - 正常返回: 写入 *forwarder.InvokeResponse 和 ok=true
func (h *APIHandler) dispatchInvokeRequest(
	c *gin.Context,
	group string,
	targetClient *client.RpcClient,
	sequence string,
	reqDataJSON []byte,
	timeout time.Duration,
	traceID string,
) (*forwarder.InvokeResponse, bool) {
	resp, err := h.waitUnaryInvoke(c.Request.Context(), group, targetClient, sequence, reqDataJSON, timeout, traceID)
	if err != nil {
		targetClient.MarkFailure()
		h.writeForwardError(c, group, targetClient.ClientID, err)
		// Timeout → ok=true so callers still record timeout metrics;
		// send/other failures → ok=false.
		if errors.Is(err, errInvokeTimeout) {
			return nil, true
		}
		return nil, false
	}
	logger.WithTraceID(traceID).Debugf("Request completed: sequence=%s, group=%s, clientId=%s", sequence, group, targetClient.ClientID)
	return resp, true
}

// renderUnaryResponse 把 InvokeResponse 渲染成统一响应信封 Response, 携带路由元数据
// group / clientId 与 trace_id。
//
// 兼容旧前端: 当客户端回的是 JSON object 时, 把它的字段平级展开到顶层而不是塞到 data 里;
// 否则当作字符串放进 data 字段。
func (h *APIHandler) renderUnaryResponse(c *gin.Context, builder RequestBuilder, group string,
	targetClient *client.RpcClient, resp *forwarder.InvokeResponse, reqAction string, startTime time.Time) {

	metricStatus := "success"
	if resp.Status < 0 || resp.Error != "" {
		metricStatus = "failure"
		targetClient.MarkFailure()
	} else {
		targetClient.MarkSuccess()
	}
	h.recordInvokeMetric(builder, group, reqAction, metricStatus, startTime)

	if resp.Error != "" {
		// 客户端返回了错误信息: 优先使用客户端给出的 status 作为业务码;
		// 若客户端没显式置错误码 (status=0), 降级为 ClientInvokeFailed, 避免
		// 把"成功码"和错误信息一起返回。
		code := resp.Status
		if code == 0 {
			code = errorcode.ClientInvokeFailed
		}
		r := Response{
			Code:     code,
			Message:  resp.Error,
			Group:    group,
			ClientID: targetClient.ClientID,
		}
		r.TraceID = traceID(c)
		c.JSON(http.StatusOK, r)
		return
	}

	message := "success"
	if resp.Status < 0 {
		// 没有 error 字符串但 status<0, 是不期望的形态, 降级成 unknown error。
		message = "unknown error"
	}

	// 成功路径: 客户端返回 JSON object 时平级展开到顶层, 否则原样放入 Data。
	var responseMap map[string]interface{}
	if err := json.Unmarshal(resp.Data, &responseMap); err == nil {
		result := gin.H{
			"code":     resp.Status,
			"message":  message,
			"group":    group,
			"clientId": targetClient.ClientID,
			"trace_id": traceID(c),
		}
		for k, v := range responseMap {
			result[k] = v
		}
		c.JSON(http.StatusOK, result)
		return
	}

	r := Response{
		Code:     resp.Status,
		Message:  message,
		Data:     string(resp.Data),
		Group:    group,
		ClientID: targetClient.ClientID,
	}
	r.TraceID = traceID(c)
	c.JSON(http.StatusOK, r)
}

// recordInvokeMetric 写一次 invoke 指标 (调用计数 + 延迟)。
// builder.ShouldRecordMetrics()/h.metricsCollector 任一缺失则跳过, unary 超时 /
// unary 完成 / stream defer 三处共用, 防止漏埋点或形态不一致。
func (h *APIHandler) recordInvokeMetric(builder RequestBuilder, group, action, status string, startTime time.Time) {
	if !builder.ShouldRecordMetrics() || h.metricsCollector == nil {
		return
	}
	metricAPI := builder.GetMetricAPI(action)
	tags := map[string]string{"group": group, "api": metricAPI, "status": status}
	h.metricsCollector.Incr("invoke.total", tags, 1)
	h.metricsCollector.RecordLatency("invoke.latency",
		map[string]string{"group": group, "api": metricAPI},
		float64(time.Since(startTime).Milliseconds()))
}

// writeForwardError 输出 invoke 路径下的错误响应包络, 携带 group / clientId 与 trace_id。
// 必须在 HTTP 响应头未写出时调用 (否则 JSON 头会失败)。
// errInvokeTimeout → errorcode.Timeout；其余 → errorcode.InternalError。
func (h *APIHandler) writeForwardError(c *gin.Context, group, clientID string, err error) {
	code := errorcode.InternalError
	if errors.Is(err, errInvokeTimeout) {
		code = errorcode.Timeout
	}
	msg := "unknown error"
	if err != nil {
		msg = err.Error()
	}
	FailWithRoute(c, code, msg, group, clientID)
}

// authorizeRegisteredGroupAccess 校验当前请求对已注册 (group_config 存在) 分组的访问权限。
//
// 鉴权链路:
//   - 调用方应先经 middleware.AuthMiddleware 鉴权, 用户信息在 context 中
//     (key = middleware.ContextUserKey)。
//   - 若分组匿名 (group_config 缺失), 放行。
//   - 若当前请求未携带任何用户凭证 (匿名调用) 且分组是注册分组, 拒绝。
//   - 否则要求当前用户是管理员或 group_config 的归属用户。
//
// 原版本同时支持调用方在 body/query 中传 sekiro_token 解析用户 — 已被删除, 鉴权
// 入口统一收敛到中间件, 业务层不再做 token 解析。
func (h *APIHandler) authorizeRegisteredGroupAccess(c *gin.Context, groupName string) bool {
	// Fail closed: without a group repository we cannot distinguish registered
	// vs anonymous groups, so deny rather than open the door.
	if h.groupRepo == nil {
		InternalError(c, "group repository not available")
		return false
	}
	if h.authMW == nil {
		InternalError(c, "auth middleware not available")
		return false
	}

	group, err := h.authMW.LookupGroupConfig(groupName)
	if err != nil {
		InternalError(c, "failed to verify group access: "+err.Error())
		return false
	}
	if group == nil {
		// 未配置 group_config，视为匿名分组放行。
		return true
	}

	user, ok := middleware.GetCurrentUser(c)
	if !ok || user == nil {
		Unauthorized(c, "registered group requires a valid sekiro token")
		return false
	}

	if !user.IsAdmin && user.UserName != group.UserName {
		Forbidden(c, "no access to registered group")
		return false
	}

	return true
}

func (h *APIHandler) filterAccessibleGroups(c *gin.Context, groups []string) ([]string, error) {
	// Fail closed: without repo we cannot filter registered groups safely.
	// Return empty rather than leaking the full online group list.
	if h.groupRepo == nil {
		return []string{}, nil
	}
	if h.authMW == nil {
		return []string{}, nil
	}

	token := middleware.ExtractAuthTokenFromRequest(c, false)
	var user *model.UserInfo
	if token != "" {
		resolved, err := h.authMW.FindUserByToken(token)
		if err == nil {
			user = resolved
			c.Set(middleware.ContextUserKey, user)
		}
	}

	filtered := make([]string, 0, len(groups))
	for _, groupName := range groups {
		group, err := h.authMW.LookupGroupConfig(groupName)
		if err != nil {
			// Fail closed on lookup errors: omit the group instead of treating
			// it as anonymous (which would leak registered group names).
			logger.Warnf("filterAccessibleGroups: lookup group_config failed for %s: %v, omitting", groupName, err)
			continue
		}
		if group == nil {
			filtered = append(filtered, groupName)
			continue
		}

		if user != nil && (user.IsAdmin || user.UserName == group.UserName) {
			filtered = append(filtered, groupName)
		}
	}

	return filtered, nil
}

// streamSSEResponse 把 StreamRecord 的 chunk 通过 chunked HTTP 以 text/event-stream 输出。
//
// 与 unary 路径的区别：
//   - 不再用 timeoutManager.Wait() 一次性拿响应；改成循环消费 ChunkChan
//   - HTTP 200 头一旦发出去就无法回退到错误状态码，失败只能用 `event: error` 通知
//   - 客户端断连（c.Request.Context().Done()）主动 RemoveStream，触发 ChunkChan close 让客户端读流终止
func (h *APIHandler) streamSSEResponse(
	c *gin.Context,
	rec *forwarder.StreamRecord,
	group string,
	targetClient *client.RpcClient,
	builder RequestBuilder,
	startTime time.Time,
	reqAction string,
) {
	WriteSSEHeaders(c)

	flusher, ok := c.Writer.(http.Flusher)
	if !ok {
		// gin 的 ResponseWriter 实现了 Flusher，理论上不会到这里
		h.timeoutManager.RemoveStream(rec.ID)
		logger.Errorf("streamSSEResponse: ResponseWriter does not implement http.Flusher")
		return
	}
	flusher.Flush() // 立即把 200 头送出去

	timeoutTimer := time.NewTimer(rec.Timeout)
	defer timeoutTimer.Stop()

	var streamErr string
	defer func() {
		if builder.ShouldRecordMetrics() && h.metricsCollector != nil {
			status := "success"
			if streamErr != "" {
				status = "failure"
			}
			metricAPI := builder.GetMetricAPI(reqAction)
			h.metricsCollector.Incr("invoke.total", map[string]string{
				"group": group, "api": metricAPI, "status": status,
			}, 1)
			h.metricsCollector.RecordLatency("invoke.latency", map[string]string{
				"group": group, "api": metricAPI,
			}, float64(time.Since(startTime).Milliseconds()))
		}
		if streamErr != "" {
			targetClient.MarkFailure()
		} else {
			targetClient.MarkSuccess()
		}
	}()

	for {
		select {
		case <-c.Request.Context().Done():
			h.timeoutManager.RemoveStream(rec.ID)
			streamErr = "client disconnected"
			return
		case <-timeoutTimer.C:
			h.timeoutManager.RemoveStream(rec.ID)
			streamErr = "timeout"
			WriteSSEErrorEvent(c.Writer, "timeout")
			flusher.Flush()
			return
		case chunk, ok := <-rec.ChunkChan:
			if !ok {
				if errMsg := rec.TerminalError(); errMsg != "" {
					streamErr = errMsg
					WriteSSEErrorEvent(c.Writer, errMsg)
					flusher.Flush()
				}
				return
			}
			if chunk.Error != "" {
				streamErr = chunk.Error
				WriteSSEErrorEvent(c.Writer, chunk.Error)
				flusher.Flush()
				continue // ChunkChan close 会从 ok=false 退出
			}
			// chunk.Data 是 json.RawMessage：
			//   - 客户端发的 data 通常是 JSON 字符串字面量（带引号），需要 Unmarshal 成 string 再写
			//   - 如果客户端发了非字符串（对象/数组），退化成原样字节透传
			if len(chunk.Data) == 0 {
				continue
			}
			payload, ok := decodeStreamBytes(chunk.Data)
			if !ok {
				continue
			}
			if _, err := c.Writer.Write(payload); err != nil {
				h.timeoutManager.RemoveStream(rec.ID)
				streamErr = "write failed: " + err.Error()
				return
			}
			flusher.Flush()
		}
	}
}

// decodeStreamBytes 把 chunk.Data (json.RawMessage) 还原成 SSE 文本字节。
// 客户端通常把 SSE 文本编码为 JSON 字符串字面量（带引号），需要 Unmarshal
// 成 string；如果发的是非字符串（对象/数组），退化成原样字节透传。
// 返回 (nil, false) 表示 chunk 是空数据。
func decodeStreamBytes(data []byte) ([]byte, bool) {
	if len(data) == 0 {
		return nil, false
	}
	var payload string
	if err := json.Unmarshal(data, &payload); err == nil {
		return []byte(payload), true
	}
	return data, true
}
