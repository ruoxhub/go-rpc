import type { AnalysisResultV2 } from "@/utils/analysis";
import { Badge, StatCard } from "../ui";
import { formatPercent, formatSeconds } from "../format";

/**
 * 总览：综合评分 featured card（本页唯一渐变边框，Brand-frame 角色）+ 关键指标。
 */
export function OverviewSection({ data }: { data: AnalysisResultV2 }) {
  const overall = data.scoring?.overall;
  const stats = [
    {
      label: "黄金 3 秒钩子",
      value: data.scoring?.hook?.score?.toFixed(1) ?? "-",
    },
    {
      label: "转化力",
      value: data.scoring?.conversion?.score?.toFixed(1) ?? "-",
    },
    {
      label: "可复制性",
      value: data.scoring?.replicability?.score?.toFixed(1) ?? "-",
    },
    {
      label: "平台契合度",
      value: data.target_definition?.platform_tone_match?.toFixed(1) ?? "-",
    },
    {
      label: "视频时长",
      value: formatSeconds(data.basic_info?.duration),
    },
    {
      label: "BGM 节奏",
      value:
        data.post_production?.rhythm?.bpm_estimate != null
          ? String(Math.round(data.post_production.rhythm.bpm_estimate))
          : "-",
      suffix: "BPM",
    },
  ];

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {/* 综合评分 —— 本屏唯一 featured card */}
      <div className="gradient-border rounded-lg p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground">
            综合评分
          </span>
          {data.meta?.confidence_overall != null ? (
            <Badge variant="primary">
              置信度 {formatPercent(data.meta.confidence_overall)}
            </Badge>
          ) : null}
        </div>
        <div className="mt-3 font-numeric text-5xl font-semibold leading-none tabular-nums">
          {overall?.score?.toFixed(1) ?? "-"}
          <span className="ml-1 text-base font-normal text-muted-foreground">
            /10
          </span>
        </div>
        {overall?.reason ? (
          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            {overall.reason}
          </p>
        ) : null}
      </div>

      {/* 关键指标 */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:col-span-2">
        {stats.map((stat) => (
          <StatCard
            key={stat.label}
            label={stat.label}
            value={stat.value}
            suffix={stat.suffix}
          />
        ))}
      </div>
    </div>
  );
}
