# 日志文件落盘设计

## 目标

zap 日志系统当前只写到 stdout/stderr，无文件持久化。增加文件落盘能力，带日志轮转（lumberjack），按运行模式切换输出对象，配置通过 config.yaml 控制。

## 依赖方向（关键约束）

config 包已 import logger 包，不能反向依赖：

```
config ──import──> logger       （现状，单向，保留）
bootstrap ─────> 读 config.LogConfig，映射成 logger.FileOptions ──> logger.InitLogger
```

logger 包自定义 `FileOptions` 结构接收配置，bootstrap 负责做 config→Options 的适配映射。logger 包零新增 import。

## 变更范围

| 文件 | 变更类型 |
|------|----------|
| `internal/utils/logger/logger.go` | 重写 InitLogger，新增 FileOptions |
| `internal/utils/logger/logger_test.go` | 新增测试 |
| `internal/config/config.go` | 新增 LogConfig 结构 + ServerConfig.Log 字段 + 默认值 + merge |
| `pkg/server/bootstrap.go` | 调用 InitLogger 时传入日志配置 |
| `config.yaml` | 新增 Log 配置块 |
| `go.mod` | 新增 lumberjack 依赖 |

## logger.go 改造

### FileOptions 结构

```go
type FileOptions struct {
    Enabled    bool   // 是否启用文件日志，false 则退回纯控制台
    Dir        string // 日志目录
    Filename   string // 日志文件名
    MaxSize    int    // 单文件最大 MB
    MaxBackups int    // 保留旧文件份数
    MaxAge     int    // 保留天数
    Compress   bool   // 是否 gzip 压缩旧文件
}
```

### InitLogger 签名变更

```go
// 旧签名
func InitLogger(debug bool)

// 新签名
func InitLogger(debug bool, fileOpts *FileOptions)
```

### 内部实现

从 `config.Build()` 改为手动 `zapcore.NewCore` + `zapcore.NewTee` 组装：

- **文件 core**: `lumberjack → zapcore.AddSync → zapcore.NewCore(jsonEncoder, fileWs, level)`
- **控制台 core**: `os.Stdout → zapcore.AddSync → zapcore.NewCore(jsonEncoder, stdoutWs, level)`
- **debug 模式**: `NewTee(控制台, 文件)` — 同时输出
- **release 模式**: 只包含文件 core — 终端静默
- **fileOpts == nil 或 Enabled == false**: 只包含控制台 core — 保持向后兼容（`init()` 中 `InitLogger(false, nil)` 仍可用）

EncoderConfig（时间格式 ISO8601、JSON 编码、字段名等）原样保留，不改变日志格式。

### 日志文件路径

组合为 `fileOpts.Dir + "/" + fileOpts.Filename`，lumberjack 接管写入和轮转。

## config.go 改造

### LogConfig 结构

```go
type LogConfig struct {
    Dir        string `yaml:"Dir"`        // 日志目录，默认 "logs"
    Filename   string `yaml:"Filename"`   // 文件名，默认 "sekiro.log"
    MaxSize    int    `yaml:"MaxSize"`    // 单文件最大 MB，默认 100
    MaxBackups int    `yaml:"MaxBackups"` // 保留旧文件份数，默认 7
    MaxAge     int    `yaml:"MaxAge"`     // 保留天数，默认 30
    Compress   bool   `yaml:"Compress"`   // gzip 压缩，默认 true
}
```

### ServerConfig 新增字段

```go
Log LogConfig `yaml:"Log"`
```

### DefaultServerConfig 默认值

```go
Log: LogConfig{
    Dir:        "logs",
    Filename:   "sekiro.log",
    MaxSize:    100,
    MaxBackups: 7,
    MaxAge:     30,
    Compress:   true,
},
```

### LoadServerConfig merge

对未设置字段用默认值填充（沿用现有 merge 模式）。注意 `MaxSize/MaxBackups/MaxAge` 的零值 `0` 无法区分"未设置"还是"故意设为 0"，因此只在值为 0 时用默认值覆盖即可。

## bootstrap.go 改造

```go
// 在 Start() 中，将 config.LogConfig 映射为 logger.FileOptions
func logFileOptions(cfg *config.LogConfig) *logger.FileOptions {
    if cfg == nil {
        return nil
    }
    return &logger.FileOptions{
        Enabled:    cfg.Dir != "" && cfg.Filename != "",
        Dir:        cfg.Dir,
        Filename:   cfg.Filename,
        MaxSize:    cfg.MaxSize,
        MaxBackups: cfg.MaxBackups,
        MaxAge:     cfg.MaxAge,
        Compress:   cfg.Compress,
    }
}

// 调用
logger.InitLogger(s.config.Debug, logFileOptions(&s.yamlConfig.Log))
```

## config.yaml 新增块

```yaml
# 日志文件配置
Log:
  Dir: "logs"
  Filename: "sekiro.log"
  MaxSize: 100      # 单文件最大 MB
  MaxBackups: 7     # 保留旧文件份数
  MaxAge: 30        # 保留天数
  Compress: true    # gzip 压缩旧文件
```

## 测试

### logger_test.go

- 传入 `FileOptions{Enabled: true}` 验证文件被创建
- debug=true 时验证有两个 core（可通过 `logger.Desugar().Core()` 或行为测试）
- release 模式下验证只有文件 core
- `FileOptions{Enabled: false}` 或 nil 时退回纯控制台
- 测试结束后清理临时文件
- `go test -race ./internal/utils/logger/...`

## 向后兼容

- `func init()` 中 `InitLogger(false, nil)` —— nil 代表无文件配置，退回纯控制台，行为与旧版一致
- 现有调用者 `logger.Debug/Info/Errorf` 等 API 不变
- `config.yaml` 不写 Log 块 → LoadServerConfig merge 默认值，文件日志自动启用到默认路径 `logs/sekiro.log`
