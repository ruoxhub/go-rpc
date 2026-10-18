import type { AnalysisResultV2 } from "@/utils/analysis";
import { EmotionCurve } from "../EmotionCurve";
import { ScoreBar } from "../ScoreBar";
import { Badge, Field, KeyValue, SectionCard } from "../ui";
import { emotionLabel, formatPercent, formatSeconds } from "../format";

/**
 * 爆款分析：传播逻辑、爆款公式、转化/传播/卖点清单、情绪曲线。
 */
export function ViralSection({ data }: { data: AnalysisResultV2 }) {
  const { viral_logic, viral_formula, conversion_points, viral_points, selling_points, emotion_arc } = data;

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        {/* 爆款逻辑 */}
        {viral_logic ? (
          <SectionCard title="爆款逻辑" description="为什么这条视频能跑量">
            <dl className="divide-y divide-border">
              <KeyValue label="留存逻辑">{viral_logic.why_retention ?? "-"}</KeyValue>
              <KeyValue label="点击逻辑">{viral_logic.why_click ?? "-"}</KeyValue>
              <KeyValue label="转化逻辑">{viral_logic.why_conversion ?? "-"}</KeyValue>
              <KeyValue label="传播逻辑">{viral_logic.why_viral ?? "-"}</KeyValue>
            </dl>
            <div className="mt-4 grid gap-4 border-t border-border pt-4">
              {viral_logic.core_selling_point ? (
                <Field label="核心卖点">{viral_logic.core_selling_point}</Field>
              ) : null}
              {viral_logic.key_conversion_action ? (
                <Field label="关键转化动作">
                  {viral_logic.key_conversion_action}
                </Field>
              ) : null}
            </div>
          </SectionCard>
        ) : null}

        {/* 爆款公式 */}
        {viral_formula ? (
          <SectionCard
            title="爆款公式"
            description="可复用的内容模板"
            extra={
              viral_formula.pattern_type ? (
                <Badge variant="primary">{viral_formula.pattern_type}</Badge>
              ) : null
            }
          >
            {viral_formula.formula_template ? (
              <div className="rounded-md bg-muted px-4 py-3 text-sm leading-6">
                {viral_formula.formula_template}
              </div>
            ) : null}

            {viral_formula.template_variables ? (
              <div className="mt-4">
                <div className="mb-2 text-xs font-medium text-muted-foreground">
                  模板变量
                </div>
                <dl className="divide-y divide-border">
                  {Object.entries(viral_formula.template_variables).map(
                    ([key, value]) => (
                      <KeyValue key={key} label={key}>
                        {value}
                      </KeyValue>
                    ),
                  )}
                </dl>
              </div>
            ) : null}

            {typeof viral_formula.replicability_score === "number" ? (
              <div className="mt-4">
                <ScoreBar
                  label="可复制性评分"
                  score={viral_formula.replicability_score}
                  emphasized
                />
              </div>
            ) : null}

            {viral_formula.success_predictors?.length ? (
              <div className="mt-4">
                <div className="mb-2 text-xs font-medium text-muted-foreground">
                  成功预测因子
                </div>
                <ul className="list-disc space-y-1 pl-5 text-sm leading-6">
                  {viral_formula.success_predictors.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {viral_formula.similar_reference_count != null ? (
              <p className="mt-4 text-xs text-muted-foreground">
                相似爆款参考样本：
                <span className="font-numeric tabular-nums">
                  {viral_formula.similar_reference_count}
                </span>{" "}
                条
              </p>
            ) : null}
          </SectionCard>
        ) : null}
      </div>

      {/* 转化点 / 传播点 / 卖点 */}
      <div className="grid gap-6 md:grid-cols-3">
        <PointList
          title="转化点"
          points={(conversion_points ?? []).map((p) => ({
            timestamp: p.timestamp,
            description: p.description,
            confidence: p.confidence,
          }))}
        />
        <PointList
          title="传播点"
          points={(viral_points ?? []).map((p) => ({
            timestamp: p.timestamp,
            description: p.description,
            confidence: p.confidence,
            meta: p.target_metric,
          }))}
        />
        <PointList
          title="卖点"
          points={(selling_points ?? []).map((p) => ({
            description: p.description,
            confidence: p.confidence,
          }))}
        />
      </div>

      {/* 情绪曲线 */}
      {emotion_arc?.intensity_curve?.length ? (
        <SectionCard
          title="情绪曲线"
          description={
            [
              emotion_arc.arc_type,
              emotion_arc.opening_emotion &&
                `开场 ${emotionLabel(emotion_arc.opening_emotion)}`,
              emotion_arc.peak_emotion &&
                `峰值 ${emotionLabel(emotion_arc.peak_emotion)}${emotion_arc.peak_timestamp != null ? ` @ ${formatSeconds(emotion_arc.peak_timestamp)}` : ""}`,
              emotion_arc.ending_emotion &&
                `收尾 ${emotionLabel(emotion_arc.ending_emotion)}`,
            ]
              .filter(Boolean)
              .join(" · ") || undefined
          }
        >
          <EmotionCurve
            curve={emotion_arc.intensity_curve}
            peakTimestamp={emotion_arc.peak_timestamp ?? undefined}
          />
          {emotion_arc.intensity_curve.some((p) => p.trigger) ? (
            <ul className="mt-4 grid gap-2 border-t border-border pt-4 text-xs leading-5 text-muted-foreground md:grid-cols-3">
              {emotion_arc.intensity_curve.map((point, index) =>
                point.trigger ? (
                  <li key={index}>
                    <span className="font-numeric tabular-nums">
                      {formatSeconds(point.timestamp)}
                    </span>{" "}
                    {point.trigger}
                  </li>
                ) : null,
              )}
            </ul>
          ) : null}
        </SectionCard>
      ) : null}
    </div>
  );
}

interface PointItem {
  timestamp?: number | null;
  description?: string | null;
  confidence?: number | null;
  meta?: string | null;
}

function PointList({ title, points }: { title: string; points: PointItem[] }) {
  return (
    <SectionCard title={title} className="h-full">
      {points.length === 0 ? (
        <p className="text-xs text-muted-foreground">暂无数据</p>
      ) : (
        <ul className="space-y-4">
          {points.map((point, index) => (
            <li key={index} className="flex gap-3">
              {point.timestamp != null ? (
                <span className="mt-0.5 inline-flex h-5 shrink-0 items-center rounded-md bg-muted px-1.5 font-numeric text-xs tabular-nums">
                  {formatSeconds(point.timestamp)}
                </span>
              ) : null}
              <div className="min-w-0">
                <p className="text-sm leading-6">{point.description}</p>
                <div className="mt-1 flex items-center gap-2">
                  {point.meta ? (
                    <Badge variant="outline">{point.meta}</Badge>
                  ) : null}
                  {point.confidence != null ? (
                    <span className="text-xs text-muted-foreground">
                      置信度 {formatPercent(point.confidence)}
                    </span>
                  ) : null}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
