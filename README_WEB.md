# Sekiro Go - Web 管理系统

## 项目概述

这是 Sekiro RPC 系统的 Go 语言实现，包含完整的 Web 管理界面。

### 技术栈

- **前端**: React 18 + Vite + Ant Design 5
- **后端**: Go + Gin + GORM
- **数据库**: PostgreSQL 14+

## 目录结构

```
sekiro-go/
├── web/                    # React 前端项目
│   ├── src/
│   │   ├── components/     # 可复用组件
│   │   ├── layouts/        # 布局组件
│   │   ├── pages/          # 页面组件
│   │   ├── utils/          # 工具函数
│   │   └── App.jsx         # 应用入口
│   ├── package.json
│   └── vite.config.js
├── pkg/
│   ├── database/           # 数据库连接
│   ├── model/              # 数据模型
│   └── server/
│       └── handlers/       # HTTP 处理器
│           ├── user.go         # 用户管理
│           ├── group.go        # 分组管理
│           ├── anonymous.go    # 匿名分组
│           ├── sysconfig.go    # 系统配置
│           ├── metric.go       # 监控指标
│           └── routes.go       # 路由配置
└── deploy/
    └── postgres/
        └── migration.sql   # PostgreSQL 迁移脚本
```

## 快速开始

### 1. 数据库设置

```bash
# 安装 PostgreSQL 14+
# 创建数据库并执行迁移脚本
psql -U postgres -f deploy/postgres/migration.sql
```

### 2. 后端启动

```bash
# 安装依赖
go mod tidy

# 配置数据库连接 (可选，使用默认配置可跳过)
# 编辑 pkg/database/database.go 或使用环境变量

# 构建并运行
go build -o sekiro-server ./cmd/server
./sekiro-server

# 或者直接运行
go run cmd/server/main.go
```

默认服务地址：http://localhost:5612

### 3. 前端开发

```bash
# 进入前端目录
cd web

# 安装依赖
npm install

# 启动开发服务器 (会自动代理到后端)
npm run dev

# 构建生产版本
npm run build
```

开发服务器地址：http://localhost:3000

## 默认账户

- 用户名：`admin`
- 密码：`admin123`

## API 端点

### 用户管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/users | 获取用户列表 |
| POST | /api/users | 添加用户 |
| PUT | /api/users/qps | 更新用户 QPS |
| DELETE | /api/users | 删除用户 |
| GET | /api/current | 获取当前用户信息 |
| POST | /api/current/password | 修改密码 |
| POST | /api/current/token/refresh | 刷新 Token |

### 分组管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/groups | 获取分组列表 |
| POST | /api/groups | 创建分组 |
| DELETE | /api/groups | 删除分组 |
| GET | /api/groups/:groupName | 获取分组详情 |
| PUT | /api/groups/qps | 更新分组 QPS |
| GET | /api/groups/:groupName/devices | 获取设备列表 |
| DELETE | /api/groups/devices | 删除设备 |
| GET | /api/groups/:groupName/actions | 获取 Action 列表 |

### 匿名分组
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/anonymous-groups | 获取匿名分组列表 |

### 系统配置
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/sysconfig | 获取配置列表 |
| PUT | /api/sysconfig | 更新配置 |
| GET | /api/sysconfig/nodes | 获取服务器节点 |
| GET | /api/sysconfig/logs | 获取系统日志 |

### 监控指标
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/metrics | 获取指标数据 |
| GET | /api/metrics/list | 获取指标列表 |
| GET | /api/metrics/dashboard | 获取大盘数据 |

## 数据库配置

默认数据库配置：
- Host: localhost
- Port: 5432
- User: postgres
- Password: postgres
- Database: sekiro
- SSLMode: disable

如需修改，请编辑 `pkg/database/database.go` 中的 `DefaultConfig()` 函数。

## 功能界面

系统包含以下功能模块：

1. **我的** - 个人中心，查看 API TOKEN、修改密码
2. **分组列表** - 管理 RPC 分组，支持创建、删除、配置 QPS
3. **匿名分组** - 查看匿名访问的分组
4. **监控指标** - 业务大盘、系统监控、MQL 编辑器、指标列表
5. **账号列表** - 用户管理，支持添加用户、配置权限、QPS 配额
6. **系统面板** - 系统配置、服务器节点、操作日志、构建信息

## 开发说明

### 添加新的 API 处理器

1. 在 `pkg/server/handlers/` 目录创建新的处理器文件
2. 实现处理器结构体和方法
3. 在 `routes.go` 中注册路由

### 添加新的前端页面

1. 在 `web/src/pages/` 目录创建新的页面组件
2. 在 `web/src/App.jsx` 中添加路由
3. 在 `web/src/layouts/Layout.jsx` 中添加菜单项

## 注意事项

- 当前实现为演示版本，部分功能使用模拟数据
- 密码存储应使用加密哈希（bcrypt 等）
- 生产环境请修改默认密码和数据库配置
- JWT/Session 认证功能待实现

## License

MIT License
