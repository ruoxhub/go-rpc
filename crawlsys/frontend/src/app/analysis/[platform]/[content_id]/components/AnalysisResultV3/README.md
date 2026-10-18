# AnalysisResultV3

本目录是视频分析详情页私有的 v3 证据评审视图。它只接收通过全局 `analysisGuards` 验证的强类型结果，不负责请求、版本分类或后端业务规则。

## 文件清单

- `index.tsx`：仅按业务优先级组合区域，保证评审决策位于所有分数之前。
- `AnalysisResultV3.test.tsx`：覆盖真实 R/G/C-only fixture、BLOCK 高分、空数组与 nullable 值。
- `components/DecisionBanner/`：门禁、评分状态、系统处置与决策原因。
- `components/EvidenceSection/`：来源、输入模式、观察覆盖、外部证据、缺口与限制。
- `components/ClassificationSection/`：主要/次要类型、拓扑、证据引用与明确评分路线。
- `components/ScoringSection/`：G0、C、单一专项分、暂定小计、诊断总分与不可评分原因。
- `components/TimelineSection/`：时间顺序、动作阶段、证据引用、主张链、商业问题与缺陷。
- `components/ReviewSection/`：补充证据、冲突、低证据状态与负责人动作。
- `components/EvidenceReferences/`：本视图内部复用的证据引用列表。
- `types/`：局部类型出口，不复制全局 wire contract。
- `utils/`：局部纯格式化、敏感标识过滤和枚举消息键映射。

## 边界与提升规则

- 不引用或复制 v2 `sections`，不展示提示词、迭代、后期制作或正式评级。
- 不在此处修复畸形 wire data；请求边界仍由 `src/utils/analysisGuards.ts` 负责。
- 无交互区域保持 Server Component；只有真实交互需求才允许增加独立 Client Component 叶子。
- 仅当同一能力被其他页面真实复用后，才提升到 `src/app/_components` 或 `src/utils`，并同步对应 README。
