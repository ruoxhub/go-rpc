# Formal Java 8 SDK

`sdk/java` 是 Java 8 WebSocket JSON client，保留现有 `RpcClient`、注册 handler 和 lifecycle
API。`start()` 只在服务端 `registered` 后 bind/ready；无自动 reconnect 或 legacy downgrade。

在应用中使用本地 JAR：

```gradle
implementation files("artifacts/sdk/go-rpc-sdk-0.1.0-experimental.1.jar")
```

本地验证：`gradlew -p sdk/java test jar`。本阶段不发布 Maven 制品；Xposed sample 仅是迁移
示例，旧 Netty/raw TCP 树保留作 legacy 参考。
