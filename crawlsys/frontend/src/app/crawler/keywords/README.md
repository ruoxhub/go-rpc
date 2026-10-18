# 关键词管理

- `page.tsx`：RSC 关键词列表，平台筛选由 URL `platform` 参数驱动。
- `new/page.tsx`：新建关键词页面。
- `[id]/edit/page.tsx`：并行加载关键词详情和含历史记录的平台数据。
- `_components/KeywordForm/`：创建、编辑表单；平台字段使用 `bs_platform_code`。
- `_components/KeywordActions/`：编辑入口与删除确认。
- `keywords.test.tsx`：筛选、CRUD、错误保留及历史平台归属测试。

关键词页面私有组件与逻辑留在本目录；确认跨模块复用后再提升。
