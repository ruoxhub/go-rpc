package router

import (
	"github.com/mrh30000/go-rpc/pkg/client"
)

// ConsistentHashStrategy 一致性 Hash 策略
type ConsistentHashStrategy struct {
	router *Router
}

// Select 根据 hash key 选择客户端
func (s *ConsistentHashStrategy) Select(group *client.RpcGroup, params RouteParams) *client.RpcClient {
	// 解析 hash key：优先使用显式设置的 HashKey
	hashKey := params.HashKey
	if hashKey == "" && shouldUseConsistentHash(params.ConstantInvoke) {
		hashKey = buildConsistentHashKey(params.GroupName, params.Action, params.Payload)
	}

	// 无 hash key 时返回 nil（让 Router 回退到 RoundRobin）
	if hashKey == "" {
		return nil
	}

	return s.router.routeByConsistentHash(group, hashKey)
}
