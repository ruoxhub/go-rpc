package router

import (
	"github.com/mrh30000/go-rpc/pkg/client"
)

// RoundRobinStrategy 轮询策略
type RoundRobinStrategy struct {
	router *Router
}

// Select 轮询选择客户端
func (s *RoundRobinStrategy) Select(group *client.RpcGroup, params RouteParams) *client.RpcClient {
	return s.router.routeByRoundRobin(group, params.ExecutorType)
}
