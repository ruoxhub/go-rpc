# SeKiRo Xposed Modern API 迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `sample/xposed` 的 Xposed 入口迁到 libxposed modern API，保留 `RpcClient` WebSocket 实现，并用模块 UI 动态配置连接参数（模块进程与注入进程双端共用）。

**Architecture:** `RpcConfig` 统一读写配置；`MainActivity` 负责表单与本机试连；`XposedMain` 改为 `XposedModule`，在 `onPackageLoaded` 中按配置启动 `RpcClient`。注册方式从 `assets/xposed_init` 改为 `META-INF/xposed/*`。

**Tech Stack:** Android Gradle、`io.github.libxposed:api:102.0.0`（compileOnly）、OkHttp3、Fastjson、JUnit4、LSPosed/Vector 运行时

**Spec:** `docs/superpowers/specifications/2026-08-04-sekiro-xposed-modern-api-design.md`

---

## File map

| Path | Responsibility |
|------|----------------|
| `sample/xposed/app/src/main/java/.../RpcConfig.java` | 配置模型 + 读写（模块 prefs；Xposed 侧优先 remote，失败降级） |
| `sample/xposed/app/src/main/java/.../XposedMain.java` | modern 入口，按配置启动 RpcClient |
| `sample/xposed/app/src/main/java/.../MainActivity.java` | 配置 UI + 保存 + 试连/断开 |
| `sample/xposed/app/src/main/java/.../ClientTimeHandler.java` | 去掉对静态 `loadPackageParam` 的依赖 |
| `sample/xposed/app/src/main/res/layout/activity_main.xml` | 配置表单布局 |
| `sample/xposed/app/src/main/resources/META-INF/xposed/java_init.list` | modern 入口类名 |
| `sample/xposed/app/src/main/resources/META-INF/xposed/scope.list` | 作用域包名 |
| `sample/xposed/app/src/main/resources/META-INF/xposed/module.prop` | 模块属性 |
| `sample/xposed/app/src/main/assets/xposed_init` | **删除**（legacy） |
| `sample/xposed/app/build.gradle` | 依赖切换 |
| `sample/xposed/app/src/main/AndroidManifest.xml` | 精简权限 + description |
| `sample/xposed/app/proguard-rules.pro` | libxposed keep 规则 |
| `sample/xposed/app/src/test/java/.../RpcConfigTest.java` | 配置默认值与校验测试 |
| `sample/xposed/README.md` | 使用说明 |

**不动：** `RpcClient.java` 及 `interfaze/Rpc*` 协议实现；go-rpc 服务端。

---

### Task 1: RpcConfig（配置模型 + 单元测试）

**Files:**
- Create: `sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/RpcConfig.java`
- Create: `sample/xposed/app/src/test/java/cn/iinti/sekiro/demoapp/RpcConfigTest.java`

- [ ] **Step 1: 写失败测试**

```java
package cn.iinti.sekiro.demoapp;

import org.junit.Test;
import static org.junit.Assert.*;

public class RpcConfigTest {
    @Test
    public void defaults_are_sane() {
        RpcConfig c = RpcConfig.defaults();
        assertEquals("127.0.0.1", c.getHost());
        assertEquals(5612, c.getPort());
        assertEquals("test", c.getGroup());
        assertTrue(c.getClientId() == null || c.getClientId().isEmpty());
        assertEquals("", c.getTargetPackage());
        assertTrue(c.isAutoStart());
    }

    @Test
    public void resolveClientId_generates_when_blank() {
        RpcConfig c = RpcConfig.defaults();
        c.setClientId("");
        String id = c.resolveClientId();
        assertNotNull(id);
        assertFalse(id.trim().isEmpty());
    }

    @Test
    public void validate_rejects_empty_host_or_group() {
        RpcConfig c = RpcConfig.defaults();
        c.setHost(" ");
        assertFalse(c.isValid());
        c.setHost("10.0.2.2");
        c.setGroup("");
        assertFalse(c.isValid());
        c.setGroup("test");
        c.setPort(0);
        assertFalse(c.isValid());
        c.setPort(5612);
        assertTrue(c.isValid());
    }
}
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd sample/xposed
./gradlew :app:testDebugUnitTest --tests cn.iinti.sekiro.demoapp.RpcConfigTest
```

Expected: FAIL（类不存在）

- [ ] **Step 3: 最小实现**

```java
package cn.iinti.sekiro.demoapp;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.UUID;

public final class RpcConfig {
    public static final String PREFS_NAME = "rpc_config";
    public static final String KEY_HOST = "host";
    public static final String KEY_PORT = "port";
    public static final String KEY_GROUP = "group";
    public static final String KEY_CLIENT_ID = "clientId";
    public static final String KEY_TARGET_PACKAGE = "targetPackage";
    public static final String KEY_AUTO_START = "autoStart";

    private String host;
    private int port;
    private String group;
    private String clientId;
    private String targetPackage;
    private boolean autoStart;

    public static RpcConfig defaults() {
        RpcConfig c = new RpcConfig();
        c.host = "127.0.0.1";
        c.port = 5612;
        c.group = "test";
        c.clientId = "";
        c.targetPackage = "";
        c.autoStart = true;
        return c;
    }

    public static RpcConfig load(SharedPreferences prefs) {
        RpcConfig c = defaults();
        if (prefs == null) {
            return c;
        }
        c.host = prefs.getString(KEY_HOST, c.host);
        c.port = prefs.getInt(KEY_PORT, c.port);
        c.group = prefs.getString(KEY_GROUP, c.group);
        c.clientId = prefs.getString(KEY_CLIENT_ID, c.clientId);
        c.targetPackage = prefs.getString(KEY_TARGET_PACKAGE, c.targetPackage);
        c.autoStart = prefs.getBoolean(KEY_AUTO_START, c.autoStart);
        return c;
    }

    public void save(SharedPreferences prefs) {
        prefs.edit()
                .putString(KEY_HOST, host == null ? "" : host.trim())
                .putInt(KEY_PORT, port)
                .putString(KEY_GROUP, group == null ? "" : group.trim())
                .putString(KEY_CLIENT_ID, clientId == null ? "" : clientId.trim())
                .putString(KEY_TARGET_PACKAGE, targetPackage == null ? "" : targetPackage.trim())
                .putBoolean(KEY_AUTO_START, autoStart)
                .apply();
    }

    /** 模块进程：普通 SharedPreferences */
    public static SharedPreferences modulePrefs(Context context) {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    public boolean isValid() {
        return host != null && !host.trim().isEmpty()
                && group != null && !group.trim().isEmpty()
                && port > 0 && port <= 65535;
    }

    public String resolveClientId() {
        if (clientId == null || clientId.trim().isEmpty()) {
            return UUID.randomUUID().toString();
        }
        return clientId.trim();
    }

    public boolean matchesTarget(String packageName) {
        if (targetPackage == null || targetPackage.trim().isEmpty()) {
            return false;
        }
        return targetPackage.trim().equals(packageName);
    }

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }
    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
    public String getGroup() { return group; }
    public void setGroup(String group) { this.group = group; }
    public String getClientId() { return clientId; }
    public void setClientId(String clientId) { this.clientId = clientId; }
    public String getTargetPackage() { return targetPackage; }
    public void setTargetPackage(String targetPackage) { this.targetPackage = targetPackage; }
    public boolean isAutoStart() { return autoStart; }
    public void setAutoStart(boolean autoStart) { this.autoStart = autoStart; }
}
```

- [ ] **Step 4: 再跑测试**

```bash
./gradlew :app:testDebugUnitTest --tests cn.iinti.sekiro.demoapp.RpcConfigTest
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/RpcConfig.java \
        sample/xposed/app/src/test/java/cn/iinti/sekiro/demoapp/RpcConfigTest.java
git commit -m "feat(xposed): add RpcConfig for shared UI/Xposed settings"
```

---

### Task 2: Gradle / Manifest / META-INF / ProGuard

**Files:**
- Modify: `sample/xposed/app/build.gradle`
- Modify: `sample/xposed/app/src/main/AndroidManifest.xml`
- Modify: `sample/xposed/app/proguard-rules.pro`
- Create: `sample/xposed/app/src/main/resources/META-INF/xposed/java_init.list`
- Create: `sample/xposed/app/src/main/resources/META-INF/xposed/scope.list`
- Create: `sample/xposed/app/src/main/resources/META-INF/xposed/module.prop`
- Delete: `sample/xposed/app/src/main/assets/xposed_init`

- [ ] **Step 1: 改 dependencies**

在 `app/build.gradle` 的 `dependencies` 中：

```gradle
// remove:
// compileOnly 'de.robv.android.xposed:api:82'

compileOnly 'io.github.libxposed:api:102.0.0'
// 若需远程 prefs 接口，可再加（运行时由框架提供，仍 compileOnly）:
// compileOnly 'io.github.libxposed:service:102.0.0'
```

若仓库解析不到 Maven Central，在 **根** `build.gradle` / `settings.gradle` 的 repositories 中确保有：

```gradle
mavenCentral()
```

- [ ] **Step 2: 精简 Manifest**

替换为（仅保留网络；模块 description 用 string 资源）：

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:tools="http://schemas.android.com/tools"
    package="cn.iinti.sekiro.demoapp">

    <uses-permission android:name="android.permission.INTERNET" />

    <application
        android:allowBackup="false"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:description="@string/xposed_description"
        android:roundIcon="@mipmap/ic_launcher_round"
        android:supportsRtl="true"
        android:theme="@style/AppTheme"
        tools:ignore="GoogleAppIndexingWarning">
        <activity android:name="cn.iinti.sekiro.demoapp.MainActivity">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

在 `res/values/strings.xml` 增加：

```xml
<string name="xposed_description">go-rpc WebSocket Xposed sample (libxposed modern API)</string>
```

- [ ] **Step 3: META-INF 三件套**

`java_init.list` 内容（单行，无空格多余）：

```text
cn.iinti.sekiro.demoapp.XposedMain
```

`scope.list` 初始占位（用户必须改成真实目标包；可多行）：

```text
com.example.target
```

`module.prop`：

```properties
minApiVersion=100
targetApiVersion=100
staticScope=true
```

- [ ] **Step 4: 删除 legacy 入口**

删除 `sample/xposed/app/src/main/assets/xposed_init`。

- [ ] **Step 5: ProGuard**

追加到 `app/proguard-rules.pro`：

```proguard
-dontwarn io.github.libxposed.annotation.**
-adaptresourcefilecontents META-INF/xposed/java_init.list
-keep,allowoptimization,allowobfuscation public class * extends io.github.libxposed.api.XposedModule {
    public <init>();
}
-keep class cn.iinti.sekiro.demoapp.RpcConfig { *; }
-keep class cn.iinti.sekiro3.business.api.** { *; }
```

- [ ] **Step 6: 同步依赖**

```bash
cd sample/xposed
./gradlew :app:dependencies --configuration compileOnlyClasspath
```

Expected: 能看到 `io.github.libxposed:api:102.0.0`（若失败，先修 repositories，再继续后续 Task）

- [ ] **Step 7: Commit**

```bash
git add sample/xposed/app/build.gradle \
        sample/xposed/app/src/main/AndroidManifest.xml \
        sample/xposed/app/src/main/res/values/strings.xml \
        sample/xposed/app/proguard-rules.pro \
        sample/xposed/app/src/main/resources/META-INF/xposed/ \
        sample/xposed/app/src/main/assets/
git commit -m "chore(xposed): switch to libxposed META-INF module packaging"
```

---

### Task 3: XposedMain 迁 modern API

**Files:**
- Modify: `sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/XposedMain.java`
- Modify: `sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/ClientTimeHandler.java`

- [ ] **Step 1: 重写 XposedMain**

完整替换为：

```java
package cn.iinti.sekiro.demoapp;

import android.content.SharedPreferences;
import android.util.Log;

import java.util.concurrent.atomic.AtomicReference;

import cn.iinti.sekiro3.business.api.RpcClient;
import cn.iinti.sekiro3.business.api.interfaze.ActionHandler;
import cn.iinti.sekiro3.business.api.interfaze.RpcRequest;
import cn.iinti.sekiro3.business.api.interfaze.RpcResponse;
import io.github.libxposed.api.XposedInterface;
import io.github.libxposed.api.XposedModule;
import io.github.libxposed.api.XposedModuleInterface;

public class XposedMain extends XposedModule {
    private static final String TAG = "go-rpc-xposed";

    /** 供 handler 读取当前进程名；不再依赖 LoadPackageParam 静态字段 */
    public static final AtomicReference<String> currentProcessName = new AtomicReference<>("");

    private final AtomicReference<RpcClient> clientRef = new AtomicReference<>();

    public XposedMain(XposedInterface base, XposedModuleInterface.ModuleLoadedParam param) {
        super(base, param);
        Log.i(TAG, "module loaded process=" + param.getProcessName());
    }

    @Override
    public void onPackageLoaded(XposedModuleInterface.PackageLoadedParam param) {
        String pkg = param.getPackageName();
        String process = param.getProcessName() != null ? param.getProcessName() : pkg;
        // 仅主进程
        if (!pkg.equals(process)) {
            return;
        }

        SharedPreferences prefs = loadPrefs();
        RpcConfig config = RpcConfig.load(prefs);
        if (!config.isAutoStart() || !config.isValid() || !config.matchesTarget(pkg)) {
            Log.i(TAG, "skip start: auto=" + config.isAutoStart()
                    + " valid=" + config.isValid()
                    + " target=" + config.getTargetPackage()
                    + " pkg=" + pkg);
            return;
        }

        currentProcessName.set(process);
        startClient(config);
    }

    private SharedPreferences loadPrefs() {
        // modern 双端共用：优先框架 remote prefs；不可用时降级为模块 Context prefs
        try {
            // 若编译期引入 service 且运行时可用，可在此换成 getRemotePreferences(PREFS_NAME)
            return getSharedPreferences(RpcConfig.PREFS_NAME, MODE_PRIVATE);
        } catch (Throwable t) {
            Log.w(TAG, "loadPrefs fallback failed", t);
            return null;
        }
    }

    private synchronized void startClient(RpcConfig config) {
        RpcClient old = clientRef.getAndSet(null);
        if (old != null) {
            try {
                old.destroy();
            } catch (Throwable ignored) {
            }
        }
        RpcClient client = new RpcClient(
                config.getGroup(),
                config.resolveClientId(),
                config.getHost(),
                config.getPort()
        );
        client.setupRpcRequestInitializer((req, registry) -> {
            registry.registerRpcHandler(new ActionHandler() {
                @Override
                public String action() {
                    return "testAction";
                }

                @Override
                public void handleRequest(RpcRequest request, RpcResponse response) {
                    response.success("ok");
                }
            });
            registry.registerRpcHandler(new ClientTimeHandler());
        });
        clientRef.set(client);
        client.start();
        Log.i(TAG, "RpcClient started group=" + config.getGroup()
                + " host=" + config.getHost() + ":" + config.getPort());
    }
}
```

> 注意：若当前 `libxposed:api:102` 的 `XposedModule` **无参构造**（框架自动 attach），以实际 API 为准：去掉自定义构造，把初始化放到 `onModuleLoaded`；上列构造签名以 Maven 文档 / 本地 AAR 为准，实现时对照 `io.github.libxposed.api.XposedModule` 源码微调，**禁止臆造不存在的方法**。

- [ ] **Step 2: 修 ClientTimeHandler**

```java
package cn.iinti.sekiro.demoapp;

import cn.iinti.sekiro3.business.api.interfaze.Action;
import cn.iinti.sekiro3.business.api.interfaze.AutoBind;
import cn.iinti.sekiro3.business.api.interfaze.RequestHandler;
import cn.iinti.sekiro3.business.api.interfaze.RpcRequest;
import cn.iinti.sekiro3.business.api.interfaze.RpcResponse;

@Action("clientTime")
public class ClientTimeHandler implements RequestHandler {
    @AutoBind
    private String param1;

    @AutoBind
    private Integer sleep;

    @Override
    public void handleRequest(RpcRequest sekiroRequest, RpcResponse sekiroResponse) {
        if (sleep != null && sleep > 0) {
            try {
                Thread.sleep(sleep * 1000L);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
        String process = XposedMain.currentProcessName.get();
        if (process == null || process.isEmpty()) {
            process = "unknown";
        }
        sekiroResponse.success("process: " + process + " : now:" + System.currentTimeMillis()
                + " your param1:" + param1);
    }
}
```

- [ ] **Step 3: 编译模块**

```bash
cd sample/xposed
./gradlew :app:assembleDebug
```

Expected: BUILD SUCCESSFUL  
若构造器/API 签名报错：按本机 `libxposed` API 调整 `XposedMain` 后重跑，直到通过。

- [ ] **Step 4: Commit**

```bash
git add sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/XposedMain.java \
        sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/ClientTimeHandler.java
git commit -m "feat(xposed): migrate entry to libxposed XposedModule"
```

---

### Task 4: MainActivity 配置 UI + 试连

**Files:**
- Modify: `sample/xposed/app/src/main/res/layout/activity_main.xml`
- Modify: `sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/MainActivity.java`
- Modify: `sample/xposed/app/src/main/res/values/strings.xml`（按钮文案）

- [ ] **Step 1: 布局**

`activity_main.xml` 使用纵向 `ScrollView` + 字段：

- host / port / group / clientId / targetPackage
- autoStart CheckBox
- 按钮：`保存`、`本机试连`、`断开`

控件 id 约定：`et_host`, `et_port`, `et_group`, `et_client_id`, `et_target_package`, `cb_auto_start`, `btn_save`, `btn_connect`, `btn_disconnect`, `tv_status`

- [ ] **Step 2: MainActivity 逻辑**

```java
package cn.iinti.sekiro.demoapp;

import android.app.Activity;
import android.os.Bundle;
import android.support.annotation.Nullable;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import java.util.concurrent.atomic.AtomicReference;

import cn.iinti.sekiro3.business.api.RpcClient;

public class MainActivity extends Activity {
    private final AtomicReference<RpcClient> localClient = new AtomicReference<>();

    private EditText etHost, etPort, etGroup, etClientId, etTarget;
    private CheckBox cbAutoStart;
    private TextView tvStatus;

    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        etHost = findViewById(R.id.et_host);
        etPort = findViewById(R.id.et_port);
        etGroup = findViewById(R.id.et_group);
        etClientId = findViewById(R.id.et_client_id);
        etTarget = findViewById(R.id.et_target_package);
        cbAutoStart = findViewById(R.id.cb_auto_start);
        tvStatus = findViewById(R.id.tv_status);
        Button btnSave = findViewById(R.id.btn_save);
        Button btnConnect = findViewById(R.id.btn_connect);
        Button btnDisconnect = findViewById(R.id.btn_disconnect);

        bindFrom(RpcConfig.load(RpcConfig.modulePrefs(this)));

        btnSave.setOnClickListener(v -> {
            RpcConfig c = readForm();
            if (!c.isValid()) {
                Toast.makeText(this, "host/group/port 无效", Toast.LENGTH_SHORT).show();
                return;
            }
            c.save(RpcConfig.modulePrefs(this));
            tvStatus.setText("已保存");
        });

        btnConnect.setOnClickListener(v -> {
            RpcConfig c = readForm();
            if (!c.isValid()) {
                Toast.makeText(this, "配置无效", Toast.LENGTH_SHORT).show();
                return;
            }
            c.save(RpcConfig.modulePrefs(this));
            new Thread(() -> startLocal(c), "rpc-connect").start();
        });

        btnDisconnect.setOnClickListener(v -> new Thread(this::stopLocal, "rpc-disconnect").start());
    }

    private void bindFrom(RpcConfig c) {
        etHost.setText(c.getHost());
        etPort.setText(String.valueOf(c.getPort()));
        etGroup.setText(c.getGroup());
        etClientId.setText(c.getClientId());
        etTarget.setText(c.getTargetPackage());
        cbAutoStart.setChecked(c.isAutoStart());
    }

    private RpcConfig readForm() {
        RpcConfig c = RpcConfig.defaults();
        c.setHost(etHost.getText().toString());
        try {
            c.setPort(Integer.parseInt(etPort.getText().toString().trim()));
        } catch (NumberFormatException e) {
            c.setPort(0);
        }
        c.setGroup(etGroup.getText().toString());
        c.setClientId(etClientId.getText().toString());
        c.setTargetPackage(etTarget.getText().toString());
        c.setAutoStart(cbAutoStart.isChecked());
        return c;
    }

    private void startLocal(RpcConfig c) {
        stopLocal();
        RpcClient client = new RpcClient(c.getGroup(), c.resolveClientId(), c.getHost(), c.getPort());
        client.setupRpcRequestInitializer((req, registry) -> {
            registry.registerRpcHandler(new ClientTimeHandler());
            registry.registerRpcHandler(new cn.iinti.sekiro3.business.api.interfaze.ActionHandler() {
                @Override public String action() { return "testAction"; }
                @Override public void handleRequest(
                        cn.iinti.sekiro3.business.api.interfaze.RpcRequest r,
                        cn.iinti.sekiro3.business.api.interfaze.RpcResponse s) {
                    s.success("ok");
                }
            });
        });
        localClient.set(client);
        client.start();
        runOnUiThread(() -> tvStatus.setText("试连已 start，等待 connected…"));
    }

    private void stopLocal() {
        RpcClient old = localClient.getAndSet(null);
        if (old != null) {
            old.destroy();
        }
        runOnUiThread(() -> tvStatus.setText("已断开"));
    }

    @Override
    protected void onDestroy() {
        stopLocal();
        super.onDestroy();
    }
}
```

- [ ] **Step 3: 编译**

```bash
./gradlew :app:assembleDebug
```

Expected: BUILD SUCCESSFUL

- [ ] **Step 4: 手动联调检查清单（写进 README 前先自测）**

1. 启动 go-rpc：`go run cmd/server/main.go -port 5612`
2. 安装 debug APK，打开模块 UI
3. 模拟器 host 填 `10.0.2.2`，点保存 + 本机试连
4. 调用：`http://127.0.0.1:5612/business/invoke?group=test&action=testAction`
5. 期望响应 `data` 为 `ok`

- [ ] **Step 5: Commit**

```bash
git add sample/xposed/app/src/main/res/layout/activity_main.xml \
        sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/MainActivity.java \
        sample/xposed/app/src/main/res/values/strings.xml
git commit -m "feat(xposed): add RpcClient config UI with local trial connect"
```

---

### Task 5: 远程 prefs 双端共用（降级写清）

**Files:**
- Modify: `sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/RpcConfig.java`
- Modify: `sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/XposedMain.java`
- Modify: `sample/xposed/README.md`

- [ ] **Step 1: 文档化策略（必须写进 README）**

```markdown
## 配置跨进程说明

1. **模块 UI 进程**：`RpcConfig.modulePrefs(context)` 写入 `rpc_config`。
2. **Xposed 注入进程**：优先使用 libxposed remote SharedPreferences（与框架 service 对齐）。
3. **降级**：若 remote 不可用，Xposed 侧读取模块 `getSharedPreferences` 可能为空——此时必须在 UI 保存后**强制杀目标 App 并确保 scope 正确**；demo 阶段可在 UI 用「本机试连」验证 go-rpc，hook 场景把 targetPackage 配成真实包名并在 Vector 中勾选作用域。
4. 真机 host 填电脑局域网 IP；模拟器填 `10.0.2.2`。
```

- [ ] **Step 2: 若引入 service 成功，在 XposedMain.loadPrefs 使用 remote API**

对照 `io.github.libxposed.service` 实际接口实现（名称以 AAR 为准），伪代码：

```java
SharedPreferences remote = /* framework remote prefs named RpcConfig.PREFS_NAME */;
if (remote != null) return remote;
return getSharedPreferences(RpcConfig.PREFS_NAME, MODE_PRIVATE);
```

MainActivity 保存时若 remote 可用，**同时** `save` 到 remote，保证 hook 进程可读。

- [ ] **Step 3: Commit**

```bash
git add sample/xposed/README.md \
        sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/RpcConfig.java \
        sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/XposedMain.java
git commit -m "docs(xposed): document dual-process config and remote prefs fallback"
```

---

### Task 6: README 与验收

**Files:**
- Modify: `sample/xposed/README.md`

- [ ] **Step 1: 在 README 顶部增加「当前实现」**

说明：

- 使用 libxposed modern API + `RpcClient` WebSocket
- 不再使用 Netty `SekiroClient` 连 go-rpc
- Vector/LSPosed 安装步骤、scope.list、UI 配置、invoke 示例
- 成功标准四条（与 design spec 一致）

- [ ] **Step 2: 单元测试全跑**

```bash
cd sample/xposed
./gradlew :app:testDebugUnitTest
```

Expected: 既有 `RpcClientTest` 等 + 新 `RpcConfigTest` 全绿

- [ ] **Step 3: 手工验收勾选**

- [ ] UI 保存 host/port/group 后重启模块 App，字段仍在
- [ ] 本机试连 + `/business/invoke?...action=testAction` 返回 ok
- [ ] 断线后客户端自动重连（RpcClient 既有逻辑）
- [ ] `assembleDebug` 成功；模块在 Vector 中可见 description

- [ ] **Step 4: Commit**

```bash
git add sample/xposed/README.md
git commit -m "docs(xposed): modern API setup and acceptance checklist"
```

---

## Spec coverage self-check

| Spec 要求 | Task |
|-----------|------|
| 迁 modern API 入口 | Task 3 |
| META-INF 注册 | Task 2 |
| build.gradle / ProGuard | Task 2 |
| Manifest 精简 | Task 2 |
| RpcClient 不动 | 全任务遵守 |
| UI 动态配置 | Task 1 + 4 |
| 双端共用配置 | Task 5 |
| ClientTimeHandler 去静态依赖 | Task 3 |
| 成功标准 / README | Task 6 |

## Placeholder / consistency check

- 无 TBD；`XposedModule` 构造以本机 API 为准已在 Task 3 注明
- 配置键名统一在 `RpcConfig` 常量
- 默认 group=`test`，与现有 invoke 示例一致

---

**Plan complete and saved to `docs/superpowers/plans/2026-08-04-sekiro-xposed-modern-api-plan.md`.**

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派生子代理，任务间人工复核  
2. **Inline Execution** — 本会话按 `executing-plans` 批量执行并设检查点  

选哪种？
