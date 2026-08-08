# Repository Guidelines

## Project Structure & Module Organization

`main.go` is the server composition root. Go packages live under `pkg/`, private helpers under `internal/`, and the external SDK under `pkg/client/sdk` (package `client`). Tests are colocated as `*_test.go`. The React frontend lives in `web/`; `web/dist/` is embedded into the Go binary. PostgreSQL migrations are under `deploy/postgres/`. `sample/demo-go/` is a separate module.

## Build, Test, and Development Commands

- `cd web && npm install && npm run build`: install frontend dependencies and create the embedded `web/dist/` assets.
- `go build ./...`: build all packages; requires `web/dist/` to exist.
- `go build -o rpc-server ./main.go`: build the server binary.
- `go test ./...`: run the complete Go test suite.
- `go test -run TestRpcPacket ./pkg/protocol/...`: run one named test.
- `Copy-Item .env.example .env; go run main.go`: start the server from the environment template; database-backed features require PostgreSQL.
- `powershell -File scripts/verify.ps1 -ImpactAnalysisEvidence "<result>"`: run the repository validation gate after GitNexus change detection; if GitNexus is unavailable, record the manual review used instead.
- `cd web && npm run dev`: start Vite on port 3000. Its proxy targets server port 5613, while the server defaults to 5612.

## Coding Style & Naming Conventions

Format Go code with `gofmt`. Keep packages lowercase and exported identifiers in PascalCase. Wrap errors with `fmt.Errorf("context: %w", err)`. Use `internal/utils/logger`, not `fmt.Println`, in production. JSON fields use `snake_case`; GORM columns require explicit tags. Inject `*gorm.DB` through `deps.AppDependencies` instead of using deprecated `database.DB`. Route all `RpcGroup` mutations through its actor command channel.

## Testing Guidelines

Use Go's `testing` package with `testify/assert`, favoring table-driven tests. Name tests `TestXxx` and keep them beside the implementation. Add regression tests for bug fixes and focused package tests for changed behavior. Most unit tests do not require PostgreSQL; database integration tests should use the scripts in `deploy/postgres/`.

## Commit & Pull Request Guidelines

History follows Conventional Commit-style subjects such as `fix:`, `feat(server):`, `refactor(handler):`, and `perf(client):`. Keep commits focused and use an imperative, specific summary. Pull requests should explain the problem and solution, link relevant issues, list verification commands, and include screenshots for frontend changes. Call out migrations, configuration changes, or compatibility risks.

## Agent and Security Notes

Before changing symbols, use GitNexus impact analysis and warn about HIGH or CRITICAL risk; run change detection before committing. Prefer CodeGraph for structural navigation and native search for literal text. Never commit credentials. The default admin credentials are development-only and must be changed in deployed environments.


## Skill Usage

- 技能来源以 `.agents/skills/` 为准。任务明确点名某个已安装 skill，或任务与其 `description` 明确匹配时，必须先完整阅读对应 `SKILL.md`，再按其中流程执行；不要引用未安装的 skill。
- 只选择覆盖任务所需的最小 skill 集合。多个 skill 同时适用时，先说明使用顺序和职责边界；skill 与用户要求冲突时，以用户要求为准。
- 编写、审查或重构代码时默认应用 `karpathy-guidelines`：先明确假设、边界和可验证成功标准，保持实现简单，仅做与需求直接相关的最小改动。
- Go：生产代码使用 `golang-patterns`；测试、基准、模糊测试或覆盖率工作使用 `golang-testing`；两者可在 Go 功能实现任务中配合使用。
- React：组件与状态设计使用 `react-patterns`；性能分析或优化使用 `react-performance`；组件、Hook 或页面测试使用 `react-testing`。
- React Native / Expo：仅在相关移动端代码存在或用户明确要求时使用 `react-native-patterns`，不要将其套用于当前 Web React 代码。
- API、后端与数据：REST 接口契约使用 `api-design`；后端架构、缓存或服务端通用模式使用 `backend-patterns`，但其中 Node.js/Next.js 专属做法不得直接套用于 Go；PostgreSQL 模式、查询、索引或安全工作使用 `postgres-patterns`。
- 模块边界、接口深度、可测试性或代码导航性设计使用 `codebase-design`；不要为局部小改动引入不必要的架构重构。
- UI 设计类 skill 职责边界：
  - `PRODUCT.md` 和 `DESIGN.md` 是项目设计宪法；任何 UI 方案、参考图、实现和审查结论都必须服从它们。
  - `design-taste-frontend` 负责从零设计全新页面、模块、组件或视觉方向，但只能在现有品牌 token、字体、圆角、组件体系、主题兼容、国际化和工程约束内发散。
  - `impeccable` 负责审查、打磨、修复或优化已有界面，并检查一致性、可访问性、主题兼容、响应式行为和反模板化表现。
  - “从零设计并落地”时，先用 `design-taste-frontend` 确定方向并实现，再用 `impeccable` 做最终审查；仅审查或修复现有设计时只用 `impeccable`。
