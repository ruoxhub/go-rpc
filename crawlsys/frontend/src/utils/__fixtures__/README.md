# Analysis fixtures

- `analysis-v2.json`：由后端 `models.results.AnalysisResult().model_dump(mode="json")` 生成，保留真实 Optional 默认 `null`。
- `analysis-v3.json`：由后端 `AnalysisResultV3.model_dump(mode="json")` 生成，包含非空 evidence、timeline、R 专项评分、supplemental evidence 与 conflict。
- `analysis-v3-c.json` / `analysis-v3-g.json`：后端合法 C-only 与 G route 正向 fixture。
- `generate_analysis_v3_fixture.py`：上述 fixture 的可复现生成器。在仓库根执行 `rtk python frontend/src/utils/__fixtures__/generate_analysis_v3_fixture.py`；生成后应运行前端 guards 测试并检查 JSON diff。

fixture 仅作为未知 API JSON 输入使用，测试不得在 guard 之前把它断言为前端结果类型。
