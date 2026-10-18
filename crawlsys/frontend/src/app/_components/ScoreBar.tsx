/**
 * 维度评分条：中性进度条；仅「综合评分」等唯一强调指标使用品牌渐变（Progress 角色）。
 */
export function ScoreBar({
  label,
  score,
  reason,
  emphasized = false,
}: {
  label: string;
  score?: number;
  reason?: string;
  emphasized?: boolean;
}) {
  const value = typeof score === "number" ? Math.min(10, Math.max(0, score)) : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs font-medium text-muted-foreground">
          {label}
        </span>
        <span className="font-numeric text-sm font-semibold tabular-nums">
          {typeof score === "number" ? score.toFixed(1) : "-"}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full ${emphasized ? "bg-gradient-back" : "bg-foreground/60"}`}
          style={{ width: `${value * 10}%` }}
        />
      </div>
      {reason ? (
        <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
          {reason}
        </p>
      ) : null}
    </div>
  );
}
