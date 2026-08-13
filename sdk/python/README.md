# Formal Python SDK

Python 3.10+ SDK 提供 WebSocket `ExecutorClient` 与单次 HTTP caller。连接必须先收到
`registered`，不支持 legacy downgrade 或 reconnect。

```python
from go_rpc import AsyncRpcHTTPClient

async with AsyncRpcHTTPClient("http://127.0.0.1:5612", timeout=10) as caller:
    data = await caller.invoke("demo", "echo", {"value": "ok"})
```

本地开发安装：`python -m pip install -e "sdk/python[dev]"`；也可安装 `artifacts/sdk` 中的
wheel 或 sdist。本阶段不发布到 PyPI，且正式实现不引入 tenacity/retry。
