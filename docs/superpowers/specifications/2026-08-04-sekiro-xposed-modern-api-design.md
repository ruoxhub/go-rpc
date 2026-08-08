---
name: sekiro-xposed-modern-api-migration
description: 将 sample/xposed 入口迁移到 libxposed modern API，保留 RpcClient WebSocket 实现，支持 UI 动态配置
---

# 2026-08-04 SeKiRo Xposed Modern API 迁移设计

## 项目概述

将 `sample/xposed` 的 Xposed 入口迁移到官方 `libxposed` modern API（`XposedModule` + `META-INF` 方式），同时保留现有的 `RpcClient` WebSocket 实现。

**核心原则**：
- Xposed 只负责注入 + 注册模块，不再负责 RPC 逻辑
- RpcClient 完全不动
- UI 动态配置跨端共享（模块 UI + Xposed 注入目标进程）

## 架构

```text
MainActivity (配置界面)
  ↓ 保存到 libxposed remote SharedPreferences
XposedModule.onModuleLoaded()
  ↓ 读取 prefs
  ↓ 匹配目标包名 + 进程名
  ↓ 创建 RpcClient(config)
  ↓ 连接 go-rpc
  ↓ 通过 initializer 注册 action
```

## 组件

- **RpcConfig**：读写配置的单一入口（UI 与 Xposed 共用）
- **MainActivity**：表单 + 保存 + 可选「本机试连」
- **XposedMain**：modern 入口，加载时读 config
- **RpcClient**：保持不变

## 数据流

1. 用户在 MainActivity 修改配置并保存
2. 模块加载时 onModuleLoaded() → 读取 Remote SharedPreferences
3. 匹配目标包名 + 进程名时创建 RpcClient(config)
4. 连接成功后通过 initializer 注册 action
5. go-rpc 收到 /business/invoke → handlerRegistry → RpcResponse

## 错误处理

- 连接失败：指数退避重连（不卡死主线程）
- 注册 action 失败：只 log，不影响后续运行
- 断线：不 crash，保持可重连状态
- 目标包名不匹配：静默不启动
- 权限/配置错误：直接 crash 并在 Logcat 报详细信息

## 成功标准

1. 本地 go-rpc 收到 /business/invoke 能返回 `ok`
2. 模块 UI 修改配置后，重启目标 App 仍生效
3. 断线后 5 秒内可自动重连
4. 模块卸载时能安全 `disconnect()` + 清理 prefs（幂等）

## 实施清单

1. 修改 XposedMain.java 为 modern API 风格
2. 新增 META-INF/xposed/java_init.list
3. 新增 scope.list 和 module.prop
4. 更新 AndroidManifest.xml（去掉不必要权限）
5. 更新 build.gradle（compileOnly 换 libxposed:api）
6. 添加 libxposed 官方 ProGuard 规则
7. 更新 README（Vector/LSPosed + modern API 使用方式）
8. 补 ClientTimeHandler.java（移除静态 loadPackageParam 依赖）

## 注意事项

- 目标包名需在 scope.list 里写明确
- 建议先在普通 Android App 里用 MainActivity 做本机试连
- 模块卸载时注意清理 prefs（幂等）

---
**Why:** 基于上一轮对话中用户确认的「直接迁到 libxposed modern API」 + 「双端共用配置」要求。  
**How to apply:** 直接按以上清单修改文件即可。 

**Next step:** 待用户审阅后，调用 writing-plans 技能创建实施计划。