# 阶段 1: 构建前端
FROM node:20-alpine AS frontend

WORKDIR /web

# 复制前端依赖描述文件,利用 Docker 层缓存
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund

# 复制前端源码并构建
COPY web/ ./
RUN npm run build
# 构建产物输出在 /web/dist

# 阶段 2: 构建后端
FROM golang:1.25-alpine AS builder

WORKDIR /build

# 安装依赖
RUN apk add --no-cache git ca-certificates

# 配置 Go 代理 (加速下载)
ENV GOPROXY=https://goproxy.cn,direct

# 复制 go.mod 和 go.sum
COPY go.mod go.sum ./
RUN go mod download

# 复制源代码
COPY . .

# 复制前端构建产物到 web/dist (//go:embed dist 需要)
COPY --from=frontend /web/dist ./web/dist

# 注入版本号 (可通过 --build-arg 覆盖)
ARG VERSION=dev
# 编译服务器 (静态链接，禁用 CGO);入口在仓库根目录 main.go
RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags="-w -s -X main.version=${VERSION}" \
    -o rpc-server .

# 阶段 3: 运行
FROM alpine:3.19

WORKDIR /app

# 安装必要的运行时依赖
RUN apk add --no-cache ca-certificates tzdata wget

# 从构建阶段复制二进制文件
COPY --from=builder /build/rpc-server /app/rpc-server

# 创建数据目录
RUN mkdir -p /app/data

EXPOSE 5612

# 健康检查 (使用免鉴权的 /live 端点)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:5612/live || exit 1

CMD ["/app/rpc-server"]
