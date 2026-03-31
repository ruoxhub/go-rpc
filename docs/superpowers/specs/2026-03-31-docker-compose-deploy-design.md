# Docker Compose 部署设计文档

**创建日期**: 2026-03-31
**状态**: 已批准
**作者**: Sekiro Go Team

---

## 1. 概述

本文档描述 Sekiro RPC Go 项目的 Docker Compose 生产环境部署方案，包含服务器、PostgreSQL 数据库及相关的运维配置。

### 1.1 部署目标

- **生产就绪**：完整的健康检查、日志、数据持久化
- **简化运维**：一条命令启动完整服务栈
- **配置灵活**：通过环境变量管理配置，支持不同部署场景
- **数据安全**：数据库持久化到宿主机，支持备份

### 1.2 部署架构

```
┌─────────────────────────────────────────────────────────┐
│                     Docker Compose                       │
│  ┌─────────────────────────────────────────────────┐    │
│  │              sekiro-server 容器                   │    │
│  │  - 多阶段构建 (Go 1.25 + Alpine 运行时)            │    │
│  │  - 挂载 config.yaml 配置文件                      │    │
│  │  - 端口：5612 (HTTP/WebSocket API)                │    │
│  │  - 健康检查：/business/groupList                  │    │
│  │  - 依赖：postgres (等待数据库就绪)                 │    │
│  └─────────────────────────────────────────────────┘    │
│                        │                                 │
│                        │ Docker 内部网络                  │
│                        ▼                                 │
│  ┌─────────────────────────────────────────────────┐    │
│  │              postgres 容器                        │    │
│  │  - PostgreSQL 15 (官方镜像)                       │    │
│  │  - 端口：5432 (仅内部访问，不暴露)                 │    │
│  │  - 数据持久化：./data/postgres 挂载到 /var/lib/postgresql/data │
│  │  - 健康检查：pg_isready                           │    │
│  │  - 初始化：自动执行 migration.sql                 │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 文件结构

```
sekiro-go/
├── docker-compose.yaml          # Docker Compose 主配置
├── .env                         # 环境变量 (不提交到 git)
├── .env.example                 # 环境变量模板
├── Dockerfile                   # 多阶段构建配置
├── docker-compose.override.yaml # 开发环境覆盖配置 (可选)
└── docker/
    └── init/
        └── init-db.sh           # 数据库初始化脚本
```

---

## 3. 配置文件详解

### 3.1 Dockerfile (多阶段构建)

```dockerfile
# 阶段 1: 构建
FROM golang:1.25-alpine AS builder

WORKDIR /build

# 安装依赖
RUN apk add --no-cache git ca-certificates

# 复制 go.mod 和 go.sum
COPY go.mod go.sum ./
RUN go mod download

# 复制源代码
COPY . .

# 编译服务器 (静态链接，禁用 CGO)
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o sekiro-server ./cmd/server

# 阶段 2: 运行
FROM alpine:3.19

WORKDIR /app

# 安装必要的运行时依赖
RUN apk add --no-cache ca-certificates tzdata

# 从构建阶段复制二进制文件
COPY --from=builder /build/sekiro-server /app/sekiro-server
COPY --from=builder /build/config.yaml.example /app/config.yaml

# 创建数据目录
RUN mkdir -p /app/data

EXPOSE 5612

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:5612/business/groupList || exit 1

CMD ["/app/sekiro-server"]
```

### 3.2 docker-compose.yaml

```yaml
version: '3.8'

services:
  sekiro-server:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: sekiro-server
    restart: unless-stopped
    ports:
      - "${SEKIRO_PORT:-5612}:5612"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Asia/Shanghai
    env_file:
      - .env
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./logs:/app/logs
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - sekiro-network
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:5612/business/groupList"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  postgres:
    image: postgres:15-alpine
    container_name: sekiro-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - ${DATA_DIR:-./data/postgres}:/var/lib/postgresql/data
      - ./deploy/postgres/migration.sql:/docker-entrypoint-initdb.d/init.sql:ro
    networks:
      - sekiro-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-sekiro}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

networks:
  sekiro-network:
    driver: bridge
```

### 3.3 .env.example

```bash
# ===========================================
# Sekiro RPC Server Configuration
# ===========================================

# Sekiro 服务器配置
SEKIRO_PORT=5612
SEKIRO_HOST=0.0.0.0
SEKIRO_MODE=release
SEKIRO_TIMEOUT=30

# 数据库配置
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=sekiro2024
POSTGRES_DB=sekiro

# 数据持久化目录 (相对于项目根目录)
DATA_DIR=./data/postgres
```

### 3.4 config.yaml (生产环境配置)

```yaml
# 基础监听配置
BasicListen: ":5612"
Host: "0.0.0.0"
Port: 5612

# RPC 调用默认超时时间（秒）
DefaultTimeOut: 30

# 日志配置
CloseLog: false
CloseWebLog: false

# 运行模式：debug 或 release
Mode: ${SEKIRO_MODE:-release}

# 启用 CORS 跨域
Cors: true

# 数据库配置 (Docker 内部网络)
Database:
  Host: "${POSTGRES_HOST:-postgres}"
  Port: ${POSTGRES_PORT:-5432}
  User: "${POSTGRES_USER:-postgres}"
  Password: "${POSTGRES_PASSWORD:-sekiro2024}"
  DBName: "${POSTGRES_DB:-sekiro}"
  SSLMode: "disable"
```

### 3.5 docker/init/init-db.sh

```bash
#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."

# 使用 pg_isready 等待数据库就绪
while ! pg_isready -h "${POSTGRES_HOST:-postgres}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-postgres}"; do
    sleep 1
done

echo "PostgreSQL is ready!"

# 如果需要，可以在此处执行额外的初始化逻辑
echo "Database initialization complete."
```

---

## 4. 健康检查设计

### 4.1 PostgreSQL 健康检查

| 检查项 | 配置 |
|--------|------|
| **检查命令** | `pg_isready -U postgres -d sekiro` |
| **检查间隔** | 10 秒 |
| **超时时间** | 5 秒 |
| **重试次数** | 5 次 |
| **启动宽限期** | 10 秒 |

### 4.2 Sekiro Server 健康检查

| 检查项 | 配置 |
|--------|------|
| **检查命令** | `wget --spider http://localhost:5612/business/groupList` |
| **检查类型** | Docker 级 + 应用级 |
| **检查间隔** | 30 秒 |
| **超时时间** | 10 秒 |
| **重试次数** | 3 次 |
| **启动宽限期** | 10 秒 |

### 4.3 启动顺序控制

使用 `depends_on` 的 `condition: service_healthy` 确保：

1. PostgreSQL 容器先启动并通过健康检查
2. Sekiro 服务器在数据库健康后才启动
3. 应用层等待脚本确保数据库 schema 已初始化

---

## 5. 数据持久化

### 5.1 数据目录结构

```
./data/
└── postgres/
    ├── base/           # 数据库文件
    ├── global/         # 全局系统表
    ├── pg_wal/         # WAL 日志
    ├── pg_log/         # PostgreSQL 日志
    └── postgresql.conf # 自动生成的配置
```

### 5.2 备份策略

```bash
# 备份数据库
docker exec sekiro-postgres pg_dump -U postgres sekiro > backup_$(date +%Y%m%d_%H%M%S).sql

# 恢复数据库
cat backup_20260331_120000.sql | docker exec -i sekiro-postgres psql -U postgres -d sekiro
```

---

## 6. 使用指南

### 6.1 快速开始

```bash
# 1. 克隆仓库
cd sekiro-go

# 2. 复制环境变量模板
cp .env.example .env

# 3. 复制配置文件
cp config.yaml.example config.yaml

# 4. 启动服务
docker-compose up -d

# 5. 查看日志
docker-compose logs -f

# 6. 验证服务
curl http://localhost:5612/business/groupList
```

### 6.2 停止服务

```bash
# 停止并移除容器 (保留数据)
docker-compose down

# 停止并移除所有资源 (包括数据卷)
docker-compose down -v
```

### 6.3 查看状态

```bash
# 查看容器状态
docker-compose ps

# 查看资源使用
docker stats sekiro-server sekiro-postgres
```

---

## 7. 故障排查

### 7.1 常见问题

**问题 1: Sekiro 服务器无法连接数据库**

```bash
# 检查数据库是否健康
docker-compose ps

# 查看数据库日志
docker-compose logs postgres

# 测试数据库连接
docker exec sekiro-postgres psql -U postgres -d sekiro -c "SELECT 1"
```

**问题 2: 端口冲突**

```bash
# 检查端口占用
netstat -tlnp | grep 5612

# 修改 .env 中的 SEKIRO_PORT
SEKIRO_PORT=8080
```

**问题 3: 数据目录权限问题**

```bash
# 修复权限
sudo chown -R 999:999 ./data/postgres
```

---

## 8. 安全考虑

### 8.1 密码安全

- 生产环境必须修改 `.env` 中的默认密码
- 建议使用强密码生成器
- 定期轮换数据库密码

### 8.2 网络安全

- PostgreSQL 端口不暴露到宿主机
- 使用 Docker 内部网络隔离
- 生产环境建议配置防火墙规则

### 8.3 日志安全

- 应用日志挂载到宿主机
- 建议配置日志轮转
- 敏感信息脱敏处理

---

## 9. 扩展方案

### 9.1 添加 Nginx 反向代理

```yaml
nginx:
  image: nginx:alpine
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    - ./nginx/ssl:/etc/nginx/ssl:ro
  depends_on:
    - sekiro-server
```

### 9.2 添加 Prometheus 监控

```yaml
prometheus:
  image: prom/prometheus:latest
  ports:
    - "9090:9090"
  volumes:
    - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    - prometheus-data:/prometheus
```

### 9.3 多副本部署

```yaml
sekiro-server:
  deploy:
    replicas: 3
    resources:
      limits:
        cpus: '1'
        memory: 512M
```

---

## 10. 性能优化建议

| 优化项 | 建议配置 |
|--------|---------|
| **Go 编译优化** | `-ldflags="-w -s"` 减小二进制大小 |
| **Alpine 基础镜像** | 使用 Alpine 3.19 减小镜像体积 |
| **PostgreSQL 调优** | 根据内存调整 shared_buffers |
| **日志轮转** | 配置 Docker log-driver 为 json-file |
| **资源限制** | 为容器配置 CPU 和内存限制 |

---

## 11. 验收标准

- [ ] `docker-compose up -d` 成功启动所有服务
- [ ] PostgreSQL 健康检查通过
- [ ] Sekiro 服务器健康检查通过
- [ ] 数据库自动执行 migration.sql
- [ ] 数据持久化到 `./data/postgres`
- [ ] 可通过 `http://localhost:5612` 访问 API
- [ ] 日志正常输出，无错误
- [ ] `docker-compose down` 后数据保留
