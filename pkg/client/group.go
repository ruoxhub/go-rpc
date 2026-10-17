package client

import (
	"errors"
	"math/rand"
	"strings"
	"sync"

	"github.com/mrh30000/go-rpc/pkg/utils/logger"
)

// commandType represents types of group commands
type commandType int

const (
	cmdRegister commandType = iota
	cmdUnregister
	cmdGetClient
	cmdGetAllClients
	cmdAllocate
	cmdFuzzyFind
)

// groupCommand represents a command to the group goroutine
type groupCommand struct {
	typ      commandType
	client   *RpcClient
	clientID string
	callback chan commandResult
}

// commandResult holds the result of a group command
type commandResult struct {
	client  *RpcClient
	clients []*RpcClient
	err     error
}

// RpcGroup manages clients in a single group using goroutine + channel.
// 关停模型：Close() 关闭 done channel；runLoop 监听 done 自然退出；
// 所有发送方与等待方都用 select+done 防止 close-after-check 的 TOCTOU 死锁。
type RpcGroup struct {
	name        string
	commandChan chan groupCommand
	clients     map[string]*RpcClient
	order       []string
	cursor      uint64
	wg          sync.WaitGroup
	done        chan struct{}
	closeOnce   sync.Once
}

// NewRpcGroup creates a new RpcGroup
func NewRpcGroup(name string) *RpcGroup {
	g := &RpcGroup{
		name:        name,
		commandChan: make(chan groupCommand, 64),
		clients:     make(map[string]*RpcClient),
		order:       make([]string, 0, 8),
		done:        make(chan struct{}),
	}

	g.wg.Add(1)
	go g.runLoop()

	return g
}

// runLoop processes commands in a single goroutine until done is closed.
// done 关闭后，把缓冲区里残留的命令的 callback 全部回填零值结果，让等待方立即解锁。
func (g *RpcGroup) runLoop() {
	defer g.wg.Done()

	for {
		select {
		case <-g.done:
			g.drainCommands()
			g.closeAllClients()
			return
		case cmd := <-g.commandChan:
			g.handleCommand(cmd)
		}
	}
}

// handleCommand 处理单条命令。
func (g *RpcGroup) handleCommand(cmd groupCommand) {
	switch cmd.typ {
	case cmdRegister:
		if _, exists := g.clients[cmd.client.ClientID]; !exists {
			g.order = append(g.order, cmd.client.ClientID)
		}
		g.clients[cmd.client.ClientID] = cmd.client
		logger.Debugf("Client registered: group=%s, clientId=%s", g.name, cmd.client.ClientID)

	case cmdUnregister:
		if client, ok := g.clients[cmd.clientID]; ok {
			delete(g.clients, cmd.clientID)
			g.removeFromOrder(cmd.clientID)
			logger.Debugf("Client unregistered: group=%s, clientId=%s", g.name, cmd.clientID)
			// 不要在 actor 循环内关闭连接：WSConnection.Close 在半开连接上可能长时间阻塞，
			// 会把整条串行化的 commandChan 卡死，进而冻结整个分组的请求。
			// 关闭连接不修改分组状态，放独立 goroutine 安全且不影响串行化。
			go client.Close()
		}

	case cmdGetClient:
		client := g.clients[cmd.clientID]
		cmd.callback <- commandResult{client: client}

	case cmdGetAllClients:
		clients := g.snapshotClients()
		cmd.callback <- commandResult{clients: clients}

	case cmdAllocate:
		cmd.callback <- commandResult{client: g.allocate()}

	case cmdFuzzyFind:
		cmd.callback <- commandResult{client: g.fuzzyFind(cmd.clientID)}
	}
}

// allocate 从 order 队头取可用客户端，使用递增游标取模实现 O(1) 零内存分配轮询。
// 两轮优先级：健康且在线 → 任意在线。
func (g *RpcGroup) allocate() *RpcClient {
	n := len(g.order)
	if n == 0 {
		return nil
	}

	start := int(g.cursor % uint64(n))

	// 第一轮：健康且在线
	for i := 0; i < n; i++ {
		idx := (start + i) % n
		id := g.order[idx]
		client, ok := g.clients[id]
		if !ok {
			continue
		}
		if client.GetStatus() == StatusOnline && client.GetHealthStatus() {
			g.cursor = uint64(idx + 1)
			return client
		}
	}

	// 第二轮：任意在线
	for i := 0; i < n; i++ {
		idx := (start + i) % n
		id := g.order[idx]
		client, ok := g.clients[id]
		if !ok {
			continue
		}
		if client.GetStatus() == StatusOnline {
			g.cursor = uint64(idx + 1)
			return client
		}
	}

	// 无可用客户端（全部离线），返回 nil 让调用方报错
	return nil
}

// fuzzyFind 按 ClientID 子串匹配候选客户端：健康且在线优先，多个候选时随机选择。
// 无健康候选时退化为任意在线候选；无在线候选时返回 nil。
func (g *RpcGroup) fuzzyFind(substr string) *RpcClient {
	var healthy []*RpcClient
	var online []*RpcClient

	for id, c := range g.clients {
		if !strings.Contains(id, substr) {
			continue
		}
		if c.GetStatus() != StatusOnline {
			continue
		}
		online = append(online, c)
		if c.GetHealthStatus() {
			healthy = append(healthy, c)
		}
	}

	if len(healthy) > 0 {
		return healthy[rand.Intn(len(healthy))]
	}
	if len(online) > 0 {
		return online[rand.Intn(len(online))]
	}
	return nil
}

// drainCommands 在 done 关闭后回填 commandChan 中残留命令的 callback，
// 让所有等待方解除阻塞返回零值。
func (g *RpcGroup) drainCommands() {
	for {
		select {
		case cmd := <-g.commandChan:
			if cmd.callback != nil {
				// 非阻塞发送：callback 是 buffer=1 的 channel，等待方还没读时直接成功；
				// 已读走的情况下 default 落空也无影响（不该出现，但留个保险）。
				select {
				case cmd.callback <- commandResult{}:
				default:
				}
			}
		default:
			return
		}
	}
}

// closeAllClients 在 runLoop 退出前关闭所有 client。
// 关闭动作放到独立 goroutine，避免关停时逐个阻塞 actor 循环。
func (g *RpcGroup) closeAllClients() {
	for _, c := range g.clients {
		go c.Close()
	}
	g.clients = make(map[string]*RpcClient)
	g.order = nil
}

func (g *RpcGroup) snapshotClients() []*RpcClient {
	clients := make([]*RpcClient, 0, len(g.order))
	for _, clientID := range g.order {
		if c, ok := g.clients[clientID]; ok {
			clients = append(clients, c)
		}
	}
	return clients
}

func (g *RpcGroup) removeFromOrder(clientID string) {
	for i, id := range g.order {
		if id != clientID {
			continue
		}
		g.order = append(g.order[:i], g.order[i+1:]...)
		return
	}
}

// sendCommand 把命令塞进 commandChan，已关停时立即返回 false。
// select 同时监听 done 与 channel send，避免 channel 已无消费者时永久阻塞。
func (g *RpcGroup) sendCommand(cmd groupCommand) bool {
	select {
	case <-g.done:
		return false
	default:
	}

	select {
	case g.commandChan <- cmd:
		return true
	case <-g.done:
		return false
	}
}

// waitCallback 等待回调，已关停时立即返回零值。
func (g *RpcGroup) waitCallback(callback chan commandResult) commandResult {
	select {
	case r := <-callback:
		return r
	case <-g.done:
		return commandResult{}
	}
}

// Register registers a client to the group. 已关停时静默丢弃。
func (g *RpcGroup) Register(client *RpcClient) {
	g.sendCommand(groupCommand{
		typ:    cmdRegister,
		client: client,
	})
}

// Unregister unregisters a client from the group. 已关停时静默丢弃。
func (g *RpcGroup) Unregister(clientID string) {
	g.sendCommand(groupCommand{
		typ:      cmdUnregister,
		clientID: clientID,
	})
}

// GetClient gets a client by ID. 已关停时返回 nil。
func (g *RpcGroup) GetClient(clientID string) *RpcClient {
	callback := make(chan commandResult, 1)
	if !g.sendCommand(groupCommand{
		typ:      cmdGetClient,
		clientID: clientID,
		callback: callback,
	}) {
		return nil
	}
	return g.waitCallback(callback).client
}

// GetAllClients gets all clients in the group. 已关停时返回 nil。
func (g *RpcGroup) GetAllClients() []*RpcClient {
	callback := make(chan commandResult, 1)
	if !g.sendCommand(groupCommand{
		typ:      cmdGetAllClients,
		callback: callback,
	}) {
		return nil
	}
	return g.waitCallback(callback).clients
}

// AllocateClient allocates a client for invocation. 已关停时返回 nil。
func (g *RpcGroup) AllocateClient() *RpcClient {
	callback := make(chan commandResult, 1)
	if !g.sendCommand(groupCommand{
		typ:      cmdAllocate,
		callback: callback,
	}) {
		return nil
	}
	return g.waitCallback(callback).client
}

// Close closes the group and all clients. 多次调用安全。
func (g *RpcGroup) Close() {
	g.closeOnce.Do(func() {
		close(g.done)
	})
	g.wg.Wait()
}

// Name returns the group name
func (g *RpcGroup) Name() string {
	return g.name
}

// ClientCount returns the number of clients in the group. 已关停时返回 0。
func (g *RpcGroup) ClientCount() int {
	clients := g.GetAllClients()
	return len(clients)
}

// HasClient checks if a client exists in the group
func (g *RpcGroup) HasClient(clientID string) bool {
	return g.GetClient(clientID) != nil
}

// ErrNoClientAvailable is returned when no client is available
var ErrNoClientAvailable = errors.New("no client available")

// FindClientByFuzzy finds a client whose ClientID contains substr. 已关停时返回 nil。
func (g *RpcGroup) FindClientByFuzzy(substr string) *RpcClient {
	callback := make(chan commandResult, 1)
	if !g.sendCommand(groupCommand{
		typ:      cmdFuzzyFind,
		clientID: substr,
		callback: callback,
	}) {
		return nil
	}
	return g.waitCallback(callback).client
}
