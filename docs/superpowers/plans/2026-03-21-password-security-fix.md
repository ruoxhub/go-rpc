# 密码安全修复实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复密码明文存储和返回的安全问题，使用 bcrypt 哈希算法存储密码

**Architecture:** 创建一个密码工具包 (pkg/utils/password/)，提供 HashPassword 和 CheckPassword 函数。所有需要处理密码的地方调用这些函数。

**Tech Stack:** Go, bcrypt (golang.org/x/crypto/bcrypt), GORM

---

### Task 1: 创建密码工具包

**Files:**
- Create: `pkg/utils/password/password.go`

- [ ] **Step 1: 创建密码工具文件**

```bash
mkdir -p pkg/utils/password
```

- [ ] **Step 2: 编写密码哈希和验证函数**

```go
package password

import (
	"errors"

	"golang.org/x/crypto/bcrypt"
)

// HashPassword 使用 bcrypt 生成密码哈希
func HashPassword(password string) (string, error) {
	bytes, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return "", err
	}
	return string(bytes), nil
}

// CheckPassword 验证密码与哈希是否匹配
func CheckPassword(password, hash string) bool {
	err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(password))
	return err == nil
}

// ErrInvalidPassword 密码错误
var ErrInvalidPassword = errors.New("invalid password")
```

- [ ] **Step 3: 运行测试验证**

Run: `go build ./pkg/utils/password/`
Expected: 编译成功（无错误）

---

### Task 2: 修复登录响应 - 删除明文密码返回

**Files:**
- Modify: `pkg/server/handlers/login.go:45-61`

- [ ] **Step 1: 修改 HandleLogin 响应，删除 password 字段**

找到:
```go
"data": gin.H{
    "id":           user.ID,
    "userName":     user.UserName,
    "password":     user.Password, // 保留明文密码（兼容旧版）
    "lastActive":   user.LastActive.Format("2006-01-02T15:04:05"),
    // ... 其余字段
},
```

改为:
```go
"data": gin.H{
    "id":           user.ID,
    "userName":     user.UserName,
    "lastActive":   user.LastActive.Format("2006-01-02T15:04:05"),
    // ... 其余字段（删除 password 字段）
},
```

- [ ] **Step 2: 验证编译**

Run: `go build ./pkg/server/handlers/`
Expected: 编译成功

---

### Task 3: 修复登录验证 - 使用 bcrypt 验证密码

**Files:**
- Modify: `pkg/server/handlers/login.go:31-39`

- [ ] **Step 1: 添加 bcrypt 导入**

在 import 中添加:
```go
"github.com/sekiro-go/sekiro-go/pkg/utils/password"
```

- [ ] **Step 2: 修改登录验证逻辑**

找到:
```go
// 查询用户
var user model.UserInfo
if err := database.GetDB().Where("user_name = ? AND password = ?", req.UserName, req.Password).First(&user).Error; err != nil {
    c.JSON(401, gin.H{
        "status":  -1,
        "message": "用户名或密码错误",
    })
    return
}
```

改为:
```go
// 查询用户
var user model.UserInfo
if err := database.GetDB().Where("user_name = ?", req.UserName).First(&user).Error; err != nil {
    c.JSON(401, gin.H{
        "status":  -1,
        "message": "用户名或密码错误",
    })
    return
}

// 验证密码
if !password.CheckPassword(req.Password, user.Password) {
    c.JSON(401, gin.H{
        "status":  -1,
        "message": "用户名或密码错误",
    })
    return
}
```

- [ ] **Step 3: 验证编译**

Run: `go build ./pkg/server/handlers/`
Expected: 编译成功

---

### Task 4: 修复注册功能 - 存储哈希密码

**Files:**
- Modify: `pkg/server/handlers/login.go:199-210`

- [ ] **Step 1: 修改注册逻辑，存储哈希密码**

找到:
```go
now := time.Now()
user := model.UserInfo{
    UserName:   req.UserName,
    Password:   req.Password,  // 明文存储
    // ... 其余字段
}
```

改为:
```go
now := time.Now()

// 哈希密码
hashedPassword, err := password.HashPassword(req.Password)
if err != nil {
    c.JSON(500, gin.H{
        "status":  -1,
        "message": "密码加密失败",
    })
    return
}

user := model.UserInfo{
    UserName:   req.UserName,
    Password:   hashedPassword,
    // ... 其余字段
}
```

- [ ] **Step 2: 验证编译**

Run: `go build ./pkg/server/handlers/`
Expected: 编译成功

---

### Task 5: 修复添加用户功能 - 存储哈希密码

**Files:**
- Modify: `pkg/server/handlers/login.go:241-252`

- [ ] **Step 1: 修改添加用户逻辑，存储哈希密码**

找到:
```go
now := time.Now()
user := model.UserInfo{
    UserName:   req.UserName,
    Password:   req.Password,  // 明文存储
    // ... 其余字段
}
```

改为:
```go
now := time.Now()

// 哈希密码
hashedPassword, err := password.HashPassword(req.Password)
if err != nil {
    c.JSON(500, gin.H{
        "status":  -1,
        "message": "密码加密失败",
    })
    return
}

user := model.UserInfo{
    UserName:   req.UserName,
    Password:   hashedPassword,
    // ... 其余字段
}
```

- [ ] **Step 2: 验证编译**

Run: `go build ./pkg/server/handlers/`
Expected: 编译成功

---

### Task 6: 修复默认管理员密码 - 使用哈希密码

**Files:**
- Modify: `pkg/database/database.go:103-122`

- [ ] **Step 1: 添加 bcrypt 导入**

在 import 中添加:
```go
import (
    // ... 现有导入
    "github.com/sekiro-go/sekiro-go/pkg/utils/password"
)
```

- [ ] **Step 2: 修改默认管理员密码创建逻辑**

找到:
```go
func createDefaultAdminUser() error {
    var count int64
    DB.Model(&model.UserInfo{}).Where("user_name = ?", "admin").Count(&count)
    if count == 0 {
        now := time.Now()
        adminUser := model.UserInfo{
            UserName:   "admin",
            Password:   "admin123",   // 默认用户也是明文
            IsAdmin:    true,
            // ... 其余字段
        }
        return DB.Create(&adminUser).Error
    }
    return nil
}
```

改为:
```go
func createDefaultAdminUser() error {
    var count int64
    DB.Model(&model.UserInfo{}).Where("user_name = ?", "admin").Count(&count)
    if count == 0 {
        now := time.Now()
        
        // 哈希默认密码
        hashedPassword, err := password.HashPassword("admin123")
        if err != nil {
            return err
        }
        
        adminUser := model.UserInfo{
            UserName:   "admin",
            Password:   hashedPassword,
            IsAdmin:    true,
            // ... 其余字段
        }
        return DB.Create(&adminUser).Error
    }
    return nil
}
```

- [ ] **Step 3: 验证编译**

Run: `go build ./pkg/database/`
Expected: 编译成功

---

### Task 7: 运行完整构建和测试

**Files:**
- Modify: 所有修改过的文件

- [ ] **Step 1: 运行 go mod tidy 确保依赖**

Run: `go mod tidy`
Expected: 成功添加 golang.org/x/crypto 依赖

- [ ] **Step 2: 运行完整构建**

Run: `go build ./...`
Expected: 编译成功，无错误

- [ ] **Step 3: 运行相关测试**

Run: `go test ./pkg/server/handlers/... -v`
Expected: 测试通过

---

### Task 8: 提交更改

- [ ] **Step 1: 查看更改**

Run: `git diff --stat`

- [ ] **Step 2: 添加并提交**

```bash
git add pkg/utils/password/ pkg/server/handlers/login.go pkg/database/database.go go.mod
git commit -m "fix: 使用 bcrypt 哈希存储密码，修复安全问题

- 添加密码工具包 (pkg/utils/password/)
- 登录响应删除明文密码返回
- 登录验证使用 bcrypt CheckPassword
- 注册/添加用户使用 bcrypt HashPassword
- 默认管理员密码使用哈希存储"
```

---

## 依赖

- `golang.org/x/crypto/bcrypt` - 密码哈希（自动通过 go mod tidy 添加）

## 注意事项

1. **向后兼容性**: 如果生产环境已有明文密码用户，需要编写迁移脚本
2. **测试环境**: 默认管理员密码变为哈希后的 "admin123"，登录方式不变
3. **不影响其他功能**: 仅修改密码相关逻辑，不影响现有 API 功能

## 验证步骤

完成所有任务后，验证:
1. `go build ./...` 编译成功
2. `go test ./...` 测试通过
3. 登录 API 响应中不再包含 password 字段
4. 数据库中存储的是 bcrypt 哈希值（非明文）