import type { Scoring } from "@/utils/analysis";
import { ScoreBar } from "../ScoreBar";
import { SectionCard } from "../ui";

const DIMENSIONS: { key: keyof Scoring; label: string }[] = [
  { key: "overall", label: "综合评分" },
  { key: "hook", label: "黄金 3 秒钩子" },
  { key: "selling_point", label: "卖点强度" },
  { key: "conversion", label: "转化力" },
  { key: "product_display", label: "产品展示" },
  { key: "human_action", label: "人物表现" },
  { key: "emotion_impact", label: "情绪冲击" },
  { key: "composition", label: "构图" },
  { key: "camera_language", label: "镜头语言" },
  { key: "editing_rhythm", label: "剪辑节奏" },
  { key: "visual_quality", label: "画面质量" },
  { key: "style_consistency", label: "风格一致性" },
  { key: "platform_fit", label: "平台契合" },
  { key: "replicability", label: "可复制性" },
];

/** 14 维度评分墙：仅综合评分用渐变强调（Progress 角色），其余保持中性 */
export function ScoreboardSection({ scoring }: { scoring?: Scoring }) {
  if (!scoring) return null;
  return (
    <SectionCard title="维度评分" description="10 分制 · 模型逐维打分与理由">
      <div className="grid gap-x-10 gap-y-5 md:grid-cols-2">
        {DIMENSIONS.map(({ key, label }) => {
          const item = scoring[key];
          if (!item || typeof item.score !== "number") return null;
          return (
            <ScoreBar
              key={key}
              label={label}
              score={item.score}
              reason={item.reason ?? undefined}
              emphasized={key === "overall"}
            />
          );
        })}
      </div>
    </SectionCard>
  );
}
