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
RUN apk add --no-cache ca-certificates tzdata wget

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
