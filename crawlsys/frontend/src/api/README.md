# API 模块

本目录按业务域维护请求函数及其 wire 类型。请求函数复用 `src/utils/crawler/crawler-api.ts` 的公共请求器；跨业务共享类型只在确认需要时放到对应领域模块。

- `task-metadata/`：TaskForm 与 Parser 共同使用的只读任务元数据。
- `action-parser/`：动态 Parser 的领域类型与请求接口。
- `datatype/`：ORM 与解析器 DTO 数据类型 metadata 的 wire 类型与请求接口，含数据记录（行）CRUD。
