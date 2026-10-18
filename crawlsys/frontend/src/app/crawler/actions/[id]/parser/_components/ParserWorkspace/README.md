# ParserWorkspace

Action Parser 配置页的页面私有工作区，只服务
`/crawler/actions/[id]/parser`，不提升到全局组件、store 或 utils。

- `index.tsx`：Zustand Provider、selector hook、一级区域和响应式只读边界。
- `components/`：工作台内部的页面私有 UI；包含 `StatusOverview`、`SampleParamsForm`、`SampleLibrary`、`SampleInspector`、`JsonTree` 和 `DefinitionEditor`。
- `store/`：可注入的 vanilla Zustand store 与状态迁移测试。
- `types/`：首屏服务端状态和完整工作区状态。
- `utils/`：Definition、JSON Pointer 与参数 Schema 的页面私有纯函数。

只有出现跨页面真实复用后，才允许把对应能力提取到中立公共目录；后续业务区块继续按职责放入本目录的 `components/`、`store/`、`types/` 或 `utils/`。

取样组件只处理当前 Action 的真实 RPC 和服务端返回的脱敏响应；JsonTree 通过绝对 JSON Pointer 与父工作台协作，不读取或展示原始对象存储字段。

DefinitionEditor 提供结构化/高级 JSON 双视图、字段映射和保存前 Definition 校验，仍只通过页面局部 store 更新工作定义。
