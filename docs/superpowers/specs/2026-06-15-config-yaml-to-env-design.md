# 配置系统迁移：config.yaml → .env

## 目标

将服务器配置从 `config.yaml`（YAML 格式）完全迁移到 `.env`（环境变量格式），移除所有 YAML 解析代码和 `gopkg.in/yaml.v3` 依赖。

## 决策

- **方案**：直接映射到 `ServerConfig`（方案 A）—— 保持结构体不变，只改加载方式
- **环境变量前缀**：`RPC_`
- **优先级**：CLI flags > 环境变量(.env) > 硬编码默认值
- **CLI flags 保留**：`-port`、`-host`、`-debug`、`-local-debug`（移除 `-c`）
- **YAML**：完全移除，不保留后备

## 环境变量映射

| 环境变量 | 类型 | 默认值 |
|---|---|---|
| `RPC_HOST` | string | `0.0.0.0` |
| `RPC_PORT` | int | `5612` |
| `RPC_MODE` | string | `release` |
| `RPC_TIMEOUT` | int | `30` |
| `RPC_CLOSE_LOG` | bool | `false` |
| `RPC_CLOSE_WEB_LOG` | bool | `false` |
| `RPC_CORS` | bool | `true` |
| `RPC_CORS_ORIGINS` | string(逗号分隔) | 空 |
| `RPC_DISABLE_WEB_ADMIN` | bool | `false` |
| `RPC_DISABLE_METRICS` | bool | `false` |
| `RPC_DISABLE_ALERT` | bool | `false` |
| `RPC_DISABLE_DATABASE` | bool | `false` |
| `RPC_ROUTE_REPLACE_ENABLE` | bool | `false` |
| `RPC_ROUTE_REPLACE_PREFIX` | string | 空 |
| `RPC_HTTPS_ENABLE` | bool | `false` |
| `RPC_HTTPS_LISTEN` | string | `:5643` |
| `RPC_HTTPS_PEM_PATH` | string | 空 |
| `RPC_HTTPS_KEY_PATH` | string | 空 |
| `RPC_DB_HOST` | string | `localhost` |
| `RPC_DB_PORT` | int | `5432` |
| `RPC_DB_USER` | string | `postgres` |
| `RPC_DB_PASSWORD` | string | `postgres` |
| `RPC_DB_NAME` | string | `sekiro` |
| `RPC_DB_SSL_MODE` | string | `disable` |
| `RPC_LOG_DIR` | string | `logs` |
| `RPC_LOG_FILENAME` | string | `rpc.log` |
| `RPC_LOG_MAX_SIZE` | int | `100` |
| `RPC_LOG_MAX_BACKUPS` | int | `7` |
| `RPC_LOG_MAX_AGE` | int | `30` |
| `RPC_LOG_COMPRESS` | bool | `true` |
| `RPC_SMTP_HOST` | string | `localhost` |
| `RPC_SMTP_PORT` | int | `25` |
| `RPC_SMTP_USERNAME` | string | 空 |
| `RPC_SMTP_PASSWORD` | string | 空 |
| `RPC_SMTP_FROM` | string | `alert@sekiro.local` |
| `RPC_SMTP_USE_TLS` | bool | `false` |
| `RPC_PROVIDER_QWEN_TIMEOUT` | int | `120` |
| `RPC_PROVIDER_QWEN_LOG_CHUNKS` | bool | `false` |

## 加载流程

```
main()
  ├── flag.Parse()                    // 解析 CLI flags
  ├── config.LoadDotEnv()             // 读取 .env 文件（不覆盖已设置的环境变量）
  └── srv.Start()
        ├── LoadServerConfigFromEnv() // 从 os.Getenv 填充 ServerConfig
        │     ├── 先取 DefaultServerConfig() 作为基础
        │     └── 逐字段用 envString/envInt/envBool/envStringSlice 覆盖
        ├── CLI flags 覆盖（host/port/debug 非零值优先）
        └── 后续启动逻辑不变
```

`.env` 文件查找路径：当前工作目录。复用已有的 `LoadDotEnv()`。文件不存在时静默跳过。

## 代码改动

### 删除

| 文件 | 删除内容 |
|---|---|
| `internal/config/config.go` | `LoadServerConfig`、`LoadServerConfigWithFallback`、`ToYAML`、`Save`、`fileExists` 函数；`yaml` 标签改为 `env` 标签；移除 `gopkg.in/yaml.v3` import |
| `main.go` | `-c` CLI flag、`Config.ConfigPath` 字段、`loadYAMLConfig()` 方法、`applyYAMLConfig()` 方法 |
| `config.yaml` | 整个文件 |
| `config.yaml.example` | 整个文件（如存在） |
| `go.mod` / `go.sum` | `gopkg.in/yaml.v3` 依赖（仅 `config.go` 使用，`go mod tidy` 清除） |

### 新增

| 文件 | 内容 |
|---|---|
| `internal/config/env.go` | 辅助函数 `envString`、`envInt`、`envBool`、`envStringSlice` |
| `internal/config/config.go` | `LoadServerConfigFromEnv()` 函数 |
| `.env.example` | 更新为完整环境变量模板 |

### 更新

| 文件 | 改动 |
|---|---|
| `main.go` | `Start()` 调用 `config.LoadDotEnv()` + `config.LoadServerConfigFromEnv()`；CLI flags 覆盖逻辑内联 |
| `Dockerfile` | `COPY config.yaml.example` → `COPY .env.example` |
| `docker-compose.yaml` | 移除 `./config.yaml:/app/config.yaml:ro` volume 挂载（已有 `env_file: .env`） |
| `main_test.go` | 适配新加载方式（如测试引用了 YAML 相关代码） |

### 不变

- `ServerConfig` 结构体字段定义和嵌套子结构体
- 所有消费 `ServerConfig` 的代码（`handler`、`alert`、`database`、`websocket` 等）
- `internal/config/dotenv.go`（`LoadDotEnv` 及相关解析函数）

## 字段清理

- **移除 `BasicListen`**：与 `Host:Port` 功能重叠，迁移后只保留 `Host` + `Port`，监听地址由 `fmt.Sprintf("%s:%d", host, port)` 生成（与 `main.go:312` 现有逻辑一致）

## 测试策略

- 现有 `internal/config/` 测试文件需更新，移除 YAML 相关测试用例，新增 env 加载测试
- 测试通过 `t.Setenv()` 设置环境变量，验证 `LoadServerConfigFromEnv()` 正确填充各字段
- 测试默认值回退：不设置环境变量时返回 `DefaultServerConfig()` 的值
- `main_test.go` 中如涉及 YAML 加载的测试需适配
