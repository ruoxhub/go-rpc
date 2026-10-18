import type { TimelineSegment } from "@/utils/analysis";
import { Badge, Field, SectionCard } from "../ui";
import { emotionLabel, formatPercent, formatSeconds } from "../format";

/** 时间线拆解：钩子/高潮段用状态徽章标记，节点保持中性 */
export function TimelineSection({ timeline }: { timeline?: TimelineSegment[] }) {
  if (!timeline || timeline.length === 0) return null;

  return (
    <SectionCard
      title="时间线拆解"
      description="逐段动作、营销目的与情绪节奏"
    >
      <ol className="relative space-y-8 before:absolute before:bottom-2 before:left-[7px] before:top-2 before:w-px before:bg-border">
        {timeline.map((segment, index) => (
          <li key={index} className="relative pl-8">
            {/* 节点圆点 */}
            <span
              className={`absolute left-0 top-1.5 size-[15px] rounded-full border-2 ${
                segment.is_hook_segment
                  ? "border-primary bg-primary"
                  : segment.is_payoff_segment
                    ? "border-primary/50 bg-background"
                    : "border-border bg-muted"
              }`}
            />
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-numeric text-xs font-medium tabular-nums">
                {formatSeconds(segment.start_time)} –{" "}
                {formatSeconds(segment.end_time)}
              </span>
              {segment.is_hook_segment ? (
                <Badge variant="gradient">钩子</Badge>
              ) : null}
              {segment.is_payoff_segment ? (
                <Badge variant="solid-primary">高潮</Badge>
              ) : null}
              {segment.emotion_state ? (
                <Badge variant="muted">
                  {emotionLabel(segment.emotion_state)}
                  {typeof segment.emotion_intensity === "number"
                    ? ` ${segment.emotion_intensity.toFixed(1)}`
                    : ""}
                </Badge>
              ) : null}
              {segment.beat_density ? (
                <Badge variant="outline">节奏 {segment.beat_density}</Badge>
              ) : null}
              {segment.confidence != null ? (
                <span className="text-xs text-muted-foreground">
                  置信度 {formatPercent(segment.confidence)}
                </span>
              ) : null}
            </div>

            <div className="mt-3 grid gap-x-8 gap-y-4 md:grid-cols-2">
              {segment.person_action ? (
                <Field label="人物动作">{segment.person_action}</Field>
              ) : null}
              {segment.product_action ? (
                <Field label="产品动作">{segment.product_action}</Field>
              ) : null}
              {segment.action_purpose ? (
                <Field label="动作目的">{segment.action_purpose}</Field>
              ) : null}
              {segment.marketing_purpose ? (
                <Field label="营销目的">{segment.marketing_purpose}</Field>
              ) : null}
              {segment.key_frame_description ? (
                <Field label="关键帧">{segment.key_frame_description}</Field>
              ) : null}
              {segment.camera || segment.composition ? (
                <Field label="镜头 / 构图">
                  {[segment.camera, segment.composition]
                    .filter(Boolean)
                    .join(" · ")}
                </Field>
              ) : null}
            </div>

            {segment.subtitle_text ? (
              <blockquote className="mt-3 inline-block rounded-md bg-muted px-3 py-1.5 text-xs font-medium">
                “{segment.subtitle_text}”
              </blockquote>
            ) : null}
          </li>
        ))}
      </ol>
    </SectionCard>
  );
}
