# 视频分析页面

本目录承载未删除素材列表与视频分析详情。

- `page.tsx`：从 FastAPI 获取 `t_material_clean` 素材，提供平台、状态、模型筛选和分页网格。
- `_components/MaterialCover/`：通过 FastAPI 展示 MinIO 素材封面；封面缺失或加载失败时回退视频占位图。
- `[platform]/[content_id]/`：按素材组合键展示素材元数据、分析源视频和结构化分析结果。
- `[platform]/[content_id]/components/AnalysisResultV3/`：v3 强类型本地详情视图，按决策、证据、分类、暂定评分、时间线和补充复核顺序展示；内部边界见该目录 README。
- `loading.tsx` / `error.tsx`：列表加载与错误状态。

页面私有展示继续放在本目录；结构化分析区块复用 `src/app/_components/sections`。
