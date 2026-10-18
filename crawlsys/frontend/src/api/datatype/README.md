# Datatype API

- `datatype.types.ts`：ORM 与解析器 DTO 数据类型 metadata 的 wire 类型，以及数据记录（行）CRUD 的列契约、过滤与分页类型。
- `datatype.api.ts`：数据类型领域请求函数，封装列表、详情、代码内省同步、启停状态更新与行级 CRUD。

请求复用 `src/utils/crawler/crawler-api.ts` 的 `crawlerRequest`；页面不得手拼 `/datatypes` URL。
行级接口的 `pk` 一律由本模块以 JSON 查询参数编码，页面只传主键对象。
