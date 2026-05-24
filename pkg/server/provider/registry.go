package provider

import "sync"

// registry 是全局 provider 注册表。目前只在 Server.Start 阶段（加载完 yaml 后）
// 写入；运行期只读。RWMutex 是防御性保留，避免未来引入热加载/动态 disable
// 时翻车。
//
// 不要把 Register 放进 Go 的 init()——init 在 main 之前执行，拿不到 yaml 配置；
// 也无法把 timeout/log 等配置注入到具体 provider 实例。
var (
	registryMu sync.RWMutex
	registry   []Provider
)

// Register 注册一个 provider。重复注册同名 provider 会替换旧实例（便于测试）。
// 注册顺序决定 Resolve 时的优先级：先注册者先 Match。
func Register(p Provider) {
	if p == nil {
		return
	}
	registryMu.Lock()
	defer registryMu.Unlock()
	for i, existing := range registry {
		if existing.Name() == p.Name() {
			registry[i] = p
			return
		}
	}
	registry = append(registry, p)
}

// Reset 清空注册表。仅供测试使用。
func Reset() {
	registryMu.Lock()
	defer registryMu.Unlock()
	registry = nil
}

// Resolve 根据 model 名找到第一个 Match 命中的 provider。未命中返回 nil，
// 调用方应回退到旧的 `_chat_completions` 透传链路。
func Resolve(model string) Provider {
	registryMu.RLock()
	defer registryMu.RUnlock()
	for _, p := range registry {
		if p.Match(model) {
			return p
		}
	}
	return nil
}

// List 返回当前注册的所有 provider 名称（用于诊断/状态接口）。
func List() []string {
	registryMu.RLock()
	defer registryMu.RUnlock()
	names := make([]string, 0, len(registry))
	for _, p := range registry {
		names = append(names, p.Name())
	}
	return names
}
