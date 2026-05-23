## 相关模块
sample\web\content\qwen
pkg\model\openai.go
pkg\server\api\chat_completions.go
Chat2API\src\main\proxy\adapters\qwen.ts
pkg\server\bootstrap.go
## 流程
用户传入标准的openai completions格式调用rpc-server的/api/chat/completions接口，rpc-server需要处理标准的completions格式转为qwen web chat的格式，然后与浏览器web插件建立ws连接注册chat接口，web插件接收到调用的并返回stream响应，若设置了渠道的格式转换rpc-server需要处理渠道的格式转为标准的completions格式，然后将stream返回给用户。