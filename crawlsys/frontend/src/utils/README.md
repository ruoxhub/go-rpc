# 全局工具

`src/utils` 是前端唯一的全局工具目录，仅收录跨页面复用的纯工具与稳定基础设施。

- `analysis.ts`：通过 FastAPI 读取素材列表、分析详情与视频地址；服务端数据请求读取 `ANALYSIS_API_BASE_URL`，浏览器可见的缩略图 URL 始终使用同源 `/api/analysis`；`analysis_result` 在请求边界保持 `unknown`。
- `analysisGuards.ts`：完整验证页面读取的 v2/v3 wire structure，并由 `classifyAnalysisResult` 返回带强类型结果的 v3、v2 或 unavailable 分支。
- `analysis.test.ts`：覆盖无版本与显式 v2、后端 v3 wire contract、深路径畸形结果及生产 classifier 三路。
- `__fixtures__/`：后端 Pydantic `model_dump(mode="json")` 生成的真实 v2、C/R/G v3 fixtures 与可复现生成器，详见目录 README。
- `crawler/`：Crawler 管理页面共享的 API 请求基础设施，详见 `crawler/README.md`。

单页面逻辑应放在页面局部 `utils/`；新增、迁移或删除全局工具时需同步更新本文件及目标一级子目录 README。
