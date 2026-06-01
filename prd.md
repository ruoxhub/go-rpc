## 相关内容
pkg\server\provider\qwen.go
internal\promptcompat\request_normalize.go
pkg\model\openai.go
pkg\server\api\chat_completions.go
sample\web\content\qwen\api.js
pkg\server\bootstrap.go
qwenai_completions_response.txt
## 流程
用户传入标准的openai completions格式调用rpc-server的/api/chat/completions接口，rpc-server需要使用request_normalize处理标准的completions格式转为prompt，然后将prompt传入handleQwenRequest调用浏览器web插件建立ws连接注册chatCompletions接口，web插件接收到调用的并返回stream响应，qwenai_completions_response.txt的格式转为标准的completions response格式，然后将stream返回给用户。
## 测试数据
completions_request_body.json
qwenai_completions_response.txt