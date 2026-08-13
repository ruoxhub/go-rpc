# sekiro-python

使用tornado实现python的sekiro client。

## 使用方法

### sekiro Client

```python
import json
import time

from sekiro.RpcClient import RpcClient, RpcHandler, RpcResponse


class TestHandler(RpcHandler):
    def handle(self, request: json, response: RpcResponse):
        response.success("ok")


if __name__ == '__main__':
    sekiro_client = RpcClient("test-python")
    sekiro_client.register_action("testAction", TestHandler())
    sekiro_client.start()

    # 由于sekiro client运行在单独线程中，所以需要休眠一下，否则无法测试
    time.sleep(300)
```

### invoker

```python
import json

from sekiro.RpcInvoker import RpcInvoker

# client 测试
if __name__ == '__main__':
    # https://sekiro.iinti.cn/business/invoke?group=test-python&action=testAction&sekiro_token=123
    sekiro_invoker = RpcInvoker()

    response = sekiro_invoker.request("test_group_02_anonymous", "testAction", param="testparm")
    print("invoke response: " + str(json.dumps(response, ensure_ascii=False)))
```

## 注意事项

* 一般情况下，python不常用多线程结构，故RpcClient没有做多线程包装，在高并发的情况下，用户需要自身完成多线程包装（即，默认情况下，sekiro
  handler运行在某个固定的线程中,如果执行某个耗时超过，那么需要考虑转移线程才能实现高并发）。
* 由于python json库无法序列化任意对象，故如果返回数据是一个json，那么需要保证这个对象是可以被json 序列化，或者需要自行将对象转换为字典

## Formal Python SDK（Stage 1）

上面的 `sekiro` 示例保留作 legacy 参考。正式 SDK 位于 `sdk/python`，只需从仓库本地安装：

```bash
python -m pip install -e "sdk/python[dev]"
```

```python
from go_rpc import AsyncRpcHTTPClient

async with AsyncRpcHTTPClient("http://127.0.0.1:5612") as caller:
    result = await caller.invoke("demo", "echo", {"value": "ok"})
```

`ExecutorClient` 使用 WebSocket JSON，必须等 `registered` 后才 ready，不会降级；本地 wheel/sdist
可从 `artifacts/sdk` 安装，本阶段不发布到 PyPI。生产代码使用正式 client，不复制 sample 中的
重试/tenacity 逻辑。
