# Repository Guidelines

## Project Structure & Module Organization

`main.go` is the server composition root. Go packages live under `pkg/`, private helpers under `internal/`, and the external SDK under `pkg/client/sdk` (package `client`). Tests are colocated as `*_test.go`. The React frontend lives in `web/`; `web/dist/` is embedded into the Go binary. PostgreSQL migrations are under `deploy/postgres/`. `sample/demo-go/` is a separate module.

## Build, Test, and Development Commands

- `cd web && npm install && npm run build`: install frontend dependencies and create the embedded `web/dist/` assets.
- `go build ./...`: build all packages; requires `web/dist/` to exist.
- `go build -o rpc-server ./main.go`: build the server binary.
- `go test ./...`: run the complete Go test suite.
- `go test -run TestRpcPacket ./pkg/protocol/...`: run one named test.
- `go run main.go -c config.yaml`: start the server; runtime features require PostgreSQL.
- `cd web && npm run dev`: start Vite on port 3000. Its proxy targets server port 5613, while the server defaults to 5612.

## Coding Style & Naming Conventions

Format Go code with `gofmt`. Keep packages lowercase and exported identifiers in PascalCase. Wrap errors with `fmt.Errorf("context: %w", err)`. Use `internal/utils/logger`, not `fmt.Println`, in production. JSON fields use `snake_case`; GORM columns require explicit tags. Inject `*gorm.DB` through `deps.AppDependencies` instead of using deprecated `database.DB`. Route all `RpcGroup` mutations through its actor command channel.

## Testing Guidelines

Use Go's `testing` package with `testify/assert`, favoring table-driven tests. Name tests `TestXxx` and keep them beside the implementation. Add regression tests for bug fixes and focused package tests for changed behavior. Most unit tests do not require PostgreSQL; database integration tests should use the scripts in `deploy/postgres/`.

## Commit & Pull Request Guidelines

History follows Conventional Commit-style subjects such as `fix:`, `feat(server):`, `refactor(handler):`, and `perf(client):`. Keep commits focused and use an imperative, specific summary. Pull requests should explain the problem and solution, link relevant issues, list verification commands, and include screenshots for frontend changes. Call out migrations, configuration changes, or compatibility risks.

## Agent and Security Notes

Before changing symbols, use GitNexus impact analysis and warn about HIGH or CRITICAL risk; run change detection before committing. Prefer CodeGraph for structural navigation and native search for literal text. Never commit credentials. The default admin credentials are development-only and must be changed in deployed environments.
