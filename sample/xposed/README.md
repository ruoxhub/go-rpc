# go-rpc Xposed WebSocket 客户端示例

当前示例使用仓库内的 `RpcClient`，通过 WebSocket JSON 协议连接 go-rpc，
不再依赖官方 `sekiro-business-api` 的 Netty TCP 传输层。默认连接
`ws://127.0.0.1:5612/business/register`。

依赖已在 `app/build.gradle` 中配置：

```gradle
implementation 'com.squareup.okhttp3:okhttp:3.12.13'
implementation 'com.alibaba:fastjson:1.2.83'
```

最小用法见 `app/src/main/java/cn/iinti/sekiro/demoapp/XposedMain.java`。启动服务端和目标
App 后调用：

```text
http://127.0.0.1:5612/business/invoke?group=test&action=testAction
```

期望响应中的 `data` 为 `ok`。模拟器访问宿主机时，应将客户端 host 改为 `10.0.2.2`；
真机应填写运行 go-rpc 的局域网地址。

以下内容是原 Sekiro SDK 使用资料，仅作迁移参考，其中 `SekiroClient` 和
`registerSekiroHandler` 示例不适用于当前 go-rpc WebSocket 客户端。

---

> 官网地址：[https://github.com/yint-tech/sekiro-open](https://github.com/yint-tech/sekiro-open)
>
> 文档地址：[https://sekiro.iinti.cn/sekiro-doc/](https://sekiro.iinti.cn/sekiro-doc/)
>
> 服务端地址:[https://oss.iinti.cn/sekiro/sekiro-demo](https://oss.iinti.cn/sekiro/sekiro-demo)
>

#### 环境配置
```java
// 仓库
repositories {
    maven { url "https://nexus.iinti.cn/repository/maven-public/" }
}

// 依赖
implementation('cn.iinti.sekiro3.business:sekiro-business-api:1.0')

```

API查看注入分组：[https://sekiro.iinti.cn:5612/business/groupList](https://sekiro.iinti.cn:5612/business/groupList)

查看调用状态：[https://sekiro.iinti.cn:5612/business/clientQueue?group=test_xposed](https://sekiro.iinti.cn:5612/business/clientQueue?group=test_xposed)

调用地址: [https://sekiro.iinti.cn:5612/business/invoke?group=test_xposed&action=testAction](https://sekiro.iinti.cn:5612/business/invoke?group=test_xposed&action=testAction)

#### 常规方式
需要在`AndroidManifest.xml`文件添加网络权限

```xml
<!-- 添加网络权限 -->
<uses-permission android:name="android.permission.INTERNET" />
```

新建一个`hook脚本`、做为`rpc`专用地址

根据官网去测试

```java
 if (lpparam.processName.equals(lpparam.packageName)) {// 请注意，一般sekiro只作用于特定的app
            Log.i(TAG, "packageName:" + "rpc启动");
            new SekiroClient("test_xposed", UUID.randomUUID().toString())
                    .setupSekiroRequestInitializer((sekiroRequest, handlerRegistry) ->
                            handlerRegistry.registerSekiroHandler(new ActionHandler() {
                                @Override
                                public String action() {
                                    return "testAction";
                                }

                                @Override
                                public void handleRequest(SekiroRequest sekiroRequest, SekiroResponse sekiroResponse) {
                                    sekiroResponse.success("ok");// 接口处理逻辑，我们不做任何处理，直接返回字符串：ok
                                }
                            })
                    ).start();
        }
```

<img src="https://cdn.nlark.com/yuque/0/2024/png/2931069/1733814359162-6162965f-9907-4581-ab3a-968ba3ab89b8.png" width="807.3333333333334" title="" crop="0,0,1,1" id="uf7220155" class="ne-image">

#### 模块拆分式
把接口注册的逻辑单独拆分出来，方便使用一个group实现结对多个接口进行事件操作！

<img src="https://cdn.nlark.com/yuque/0/2025/png/2931069/1745137276256-9c342301-d189-4f83-805e-cc501932b4ae.png" width="338" title="" crop="0,0,1,1" id="u13a213fa" class="ne-image">

调用的时候去里面注册接口即可

<img src="https://cdn.nlark.com/yuque/0/2025/png/2931069/1745137420896-71578970-ca8a-4c7c-aba5-2e42cc432824.png" width="782" title="" crop="0,0,1,1" id="u0511f850" class="ne-image">

调用`setupSekiroRequestInitializer`方法设置`Sekiro`请求的初始化器，<font style="color:#DF2A3F;">通过</font>`<font style="color:#DF2A3F;">handlerRegistry</font>`<font style="color:#DF2A3F;">注册</font>

##### **grop组搭建**
```java
package com.luoge.xialuo1205;
import android.util.Log;
import com.luoge.xialuo1205.handler.TestXX;
import com.luoge.xialuo1205.handler.XyRpc;
import java.util.UUID;
import cn.iinti.sekiro3.business.api.SekiroClient;
import cn.iinti.sekiro3.business.api.interfaze.ActionHandler;
import cn.iinti.sekiro3.business.api.interfaze.SekiroRequest;
import cn.iinti.sekiro3.business.api.interfaze.SekiroResponse;
import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.callbacks.XC_LoadPackage;


public class HookRpc implements IXposedHookLoadPackage {
    private static final String TAG = "XlTest";

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) throws Throwable {

        Log.i(TAG, "packageName:" + lpparam.packageName);

        Log.i(TAG, "run: " + "success");
        new SekiroClient("test-android", UUID.randomUUID().toString())
                .setupSekiroRequestInitializer((sekiroRequest, handlerRegistry) ->
                        {
                            handlerRegistry.registerSekiroHandler(new XyRpc());
                        }

                ).start();

    }
}
```

##### 接口服务搭建
新建`handler`文件做为rpc调用接口

```java
package com.luoge.xialuo1205.handler;
import cn.iinti.sekiro3.business.api.interfaze.Action;
import cn.iinti.sekiro3.business.api.interfaze.RequestHandler;
import cn.iinti.sekiro3.business.api.interfaze.SekiroRequest;
import cn.iinti.sekiro3.business.api.interfaze.SekiroResponse;

@Action("testHandler")
public class XyRpc  implements RequestHandler {

    @Override
    public void handleRequest(SekiroRequest sekiroRequest, SekiroResponse sekiroResponse) {
        // 当rpc调用时返回第一个程序
        sekiroResponse.success("hello world");
    }
}

```

<img src="https://cdn.nlark.com/yuque/0/2025/png/2931069/1745137938313-278abb4e-435b-43c1-8d94-a96f26ac5253.png" width="824.6666666666666" title="" crop="0,0,1,1" id="u348c8094" class="ne-image">

地址：[http://192.168.17.210:5612/business/invoke?group=test-android&action=testHandler](http://192.168.17.210:5612/business/invoke?group=test-android&action=testHandler)

#### 实战测试
注册接口传递包资源

```java
 handlerRegistry.registerSekiroHandler(new Dachun(lpparam.classLoader));
```

新建handler做为调用文件

```java
package com.luoge.xp1219.handler;

import android.util.Log;
import cn.iinti.sekiro3.business.api.fastjson.JSONObject;
import cn.iinti.sekiro3.business.api.interfaze.Action;
import cn.iinti.sekiro3.business.api.interfaze.RequestHandler;
import cn.iinti.sekiro3.business.api.interfaze.SekiroRequest;
import cn.iinti.sekiro3.business.api.interfaze.SekiroResponse;
import de.robv.android.xposed.XposedHelpers;

@Action("dc")
public class Dachun implements RequestHandler {


    private final ClassLoader MyClassLoader;

    public Dachun(ClassLoader classLoader){
        MyClassLoader = classLoader;
    }

    @Override
    public void handleRequest(SekiroRequest sekiroRequest, SekiroResponse sekiroResponse) {

        String args1 = sekiroRequest.getString("arg1");
        String args2 = sekiroRequest.getString("arg2");
        JSONObject jsonObject = new JSONObject();
        Class<?> SignManager = XposedHelpers.findClassIfExists("cn.thecover.lib.common.manager.SignManager", this.MyClassLoader);
        Object result = XposedHelpers.callStaticMethod(SignManager, "getSign",args1 ,"",args2);
        Log.d("hook", "handleRequest: " + result);
        jsonObject.put("key", result);
        sekiroResponse.success(jsonObject);
    }
}

```

访问地址: [http://192.168.17.210:5612/business/invoke?group=test-android&action=dc&arg1=7f06a9b2-e0ca-4fc6-9cfb-01f0c0ed81d9&arg2=1752759645242](http://192.168.17.210:5612/business/invoke?group=test-android&action=dc&arg1=7f06a9b2-e0ca-4fc6-9cfb-01f0c0ed81d9&arg2=1752759645242)

<img src="https://cdn.nlark.com/yuque/0/2025/png/2931069/1754553525272-35f2054a-ae16-4ecc-941f-b11d6741f010.png" width="1552.6666666666667" title="" crop="0,0,1,1" id="WpiIZ" class="ne-image">

测试数据提取

<img src="https://cdn.nlark.com/yuque/0/2025/png/2931069/1754553985585-cf6ec439-2770-4f7a-8743-002eb79bd2f2.png" width="659.3333333333334" title="" crop="0,0,1,1" id="u75b12366" class="ne-image">



#### API接口学习
> 本章节学习<font style="color:rgb(38, 38, 38);">FastAPI框架</font>
>

<font style="color:rgb(38, 38, 38);">FastAPI 是由 Sebastián Ramirez 创建的一个用于构建 API 的现代、快速（高性能）的 Web 框架，基于标准 Python 类型提示。</font>



<img src="https://cdn.nlark.com/yuque/0/2025/png/2931069/1754554648793-b9505d89-3477-4970-bced-ff6e2dd72361.png" width="906" title="" crop="0,0,1,1" id="u37b80a24" class="ne-image">

##### 环境安装
```java
pip install fastapi
```

##### 代码样例
```java
from fastapi import FastAPI
app = FastAPI()

# --- 示例 1: 普通 API，返回 JSON 数据 ---
@app.get("/")
async def read_data():
    """
    默认情况下，FastAPI 会自动将字典/列表转换为 JSON 格式返回
    """
    return {"message": "这是一个 JSON 接口", "status": "success"}

if __name__ == "__main__":
    import uvicorn
    # 允许直接运行 python main.py 启动
    uvicorn.run(app, host="127.0.0.1", port=5000)
```

##### 代码执行
###### <font style="color:rgb(38, 38, 38);">方式一：命令行启动</font>
```java
uvicorn main:app --host 127.0.0.1 --port 5000 --reload
```

###### <font style="color:rgb(38, 38, 38);">方式二：代码内启动</font>
```java
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)
```

###### 启动配置
```java
uvicorn.run(
    app,
    host="0.0.0.0",           # 监听所有网络接口
    port=5000,                # 端口号
    reload=False,              # 自动重载（开发模式）
    workers=1,                # 多进程工作者数量
    log_level="info",         # 日志级别：critical, error, warning, info, debug, trace
    access_log=True,          # 启用访问日志
    use_colors=True,          # 彩色日志输出
    reload_dirs=["app"],      # 监控重载的目录
)

```



##### API带查询参数
```java
@app.get("/get")
async def read_data1(user_id: str):
    return {
        "message": "这是一个 JSON 接口",
        "status": "success",
        "user_id": user_id  # 使用传入的参数
    }
```

##### 带参数并验证
需要结合进行辅助实现

```java
from fastapi.params import Query
from typing import Optional
```

针对参数进行验证，并配置可选参数

```python
@app.get("/get1")
async def read_data2(
    request: Request,
    user_id: str = Query(..., # ... 表示必须参数
                         description="用户ID",
                         min_length=1,
                         max_length=8,
                         regex="^[a-zA-Z0-9_]+$",  # 只允许字母数字下划线
                         example="user123"),
    # 可选参数
    user_type: Optional[str] = Query(None, description="用户类型")
):
   return {
        "message": "这是一个 JSON 接口",
        "status": "success",
        "user_id": user_id , # 使用传入的参数
        "page": page  # 使用传入的参数
    }
```

> 访问例子：[http://localhost:5000/get1?user_id=122&user_type=123&page=2](http://localhost:5000/get1?user_id=122&user_type=123&page=2)
>

##### 多查询参数模式
对于参数比较多的情况、可以封装一个模型类来处理参数

```python
from pydantic import BaseModel, Field
class UserQueryParams(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    age: int = Field(18, ge=0, le=100)
    page: int = Field(1, ge=1, le=100)
    size: int = Field(20, ge=1, le=100,description="每页数量")
```

| <font style="color:rgb(38, 38, 38);">参数</font> | <font style="color:rgb(38, 38, 38);">全称</font> | <font style="color:rgb(38, 38, 38);">含义</font> | <font style="color:rgb(38, 38, 38);">示例</font> | <font style="color:rgb(38, 38, 38);">数学表示</font> |
| :--- | :--- | :--- | :--- | :--- |
| `<font style="color:rgb(38, 38, 38);background-color:rgba(175, 184, 193, 0.2);">gt</font>` | <font style="color:rgb(38, 38, 38);">Greater Than</font> | <font style="color:rgb(38, 38, 38);">大于</font> | `<font style="color:rgb(38, 38, 38);background-color:rgba(175, 184, 193, 0.2);">gt=0</font>` | `<font style="color:rgb(38, 38, 38);background-color:rgba(175, 184, 193, 0.2);">x > 0</font>` |
| `<font style="color:rgb(38, 38, 38);background-color:rgba(175, 184, 193, 0.2);">ge</font>` | <font style="color:rgb(38, 38, 38);">Greater than or Equal</font> | <font style="color:rgb(38, 38, 38);">大于等于</font> | `<font style="color:rgb(38, 38, 38);background-color:rgba(175, 184, 193, 0.2);">ge=1</font>` | `<font style="color:rgb(38, 38, 38);background-color:rgba(175, 184, 193, 0.2);">x ≥ 1</font>` |
| `<font style="color:rgb(38, 38, 38);background-color:rgba(175, 184, 193, 0.2);">lt</font>` | <font style="color:rgb(38, 38, 38);">Less Than</font> | <font style="color:rgb(38, 38, 38);">小于</font> | `<font style="color:rgb(38, 38, 38);background-color:rgba(175, 184, 193, 0.2);">lt=100</font>` | `<font style="color:rgb(38, 38, 38);background-color:rgba(175, 184, 193, 0.2);">x < 100</font>` |
| `<font style="color:rgb(38, 38, 38);background-color:rgba(175, 184, 193, 0.2);">le</font>` | <font style="color:rgb(38, 38, 38);">Less than or Equal</font> | <font style="color:rgb(38, 38, 38);">小于等于</font> | `<font style="color:rgb(38, 38, 38);background-color:rgba(175, 184, 193, 0.2);">le=99</font>` | `<font style="color:rgb(38, 38, 38);background-color:rgba(175, 184, 193, 0.2);">x ≤ 99</font>` |


`<font style="color:rgb(38, 38, 38);background-color:rgba(175, 184, 193, 0.2);">Depends</font>`<font style="color:rgb(38, 38, 38);"> 是 FastAPI 中的</font>**<font style="color:rgb(38, 38, 38);">依赖注入系统</font>**<font style="color:rgb(38, 38, 38);">，用于在路由函数中注入依赖项，实现代码复用、参数验证、权限检查等功能。</font>

```python
@app.get("/get2")
async def read_data3(params: UserQueryParams = Depends()):
    return {
        "message": "参数验证通过",
        "received_data": {
            "name": params.name,
            "age": params.age,
            "page": params.page,
            "size": params.size,
            "all":params.model_dump()
        }
    }
```

访问地址：[http://localhost:5000/get2?name=122122222222](http://localhost:5000/get2?name=122122222222)

##### 返回模板文件
在项目目录新建templates和static做为静态资源存储路径

```html
<!DOCTYPE html>
<html>
<head>
    <title>{{ title }}</title> <style>
        body { font-family: sans-serif; padding: 20px; }
        .highlight { color: #e91e63; font-weight: bold; }
    </style>

    <link href="{{ url_for('static', path='/css/index.css') }}" rel="stylesheet">
<!--    <link href="/static/css/index.css" rel="stylesheet">-->

</head>
<body>
    <h1>欢迎, {{ username }}!</h1>
    <p>这是一个从 <strong>templates</strong> 目录加载的页面。</p>

    <p>当前的 ID 是: <span class="highlight">{{ id }}</span></p>

    {% if is_admin %}
        <p id="user">您是管理员权限</p>
    {% else %}
        <p>您是普通用户</p>
    {% endif %}

</body>
</html>
```

`<font style="color:rgb(38, 38, 38);background-color:rgba(175, 184, 193, 0.2);">Jinja2Templates</font>`<font style="color:rgb(38, 38, 38);"> 是 FastAPI 中用于</font>**<font style="color:rgb(38, 38, 38);">模板渲染</font>**<font style="color:rgb(38, 38, 38);">的工具，它基于 Jinja2 模板引擎，让你可以返回 HTML 页面而不仅仅是 JSON 数据。</font>

```python
from fastapi.templating import Jinja2Templates

# 1. 实例化模板引擎，指定目录为 "templates"
templates = Jinja2Templates(directory="templates")

# 配置静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")
```

项目结构例子

```python
project/
├── app.py              # 主应用文件
├── templates/          # 模板目录
│   ├── index.html     # 首页模板
│   ├── user.html      # 用户页面模板
│   └── admin/         # 子目录
│       └── dashboard.html
├── static/            # 静态文件目录
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── main.js
│   └── images/
│       └── logo.png
```

python代码列子

```python
@app.get("/api")
async def read_html(request: Request):
    user_data = {
        "id": 9527,
        "username": "Gemini用户",
        "is_admin": True,
        "title": "FastAPI 模板演示"
    }
    # 2. 返回 TemplateResponse
    return templates.TemplateResponse(
        request=request,
        name="index.html",  # 模板文件名
        context=user_data  # 传给模板的数据字典
    )
```




