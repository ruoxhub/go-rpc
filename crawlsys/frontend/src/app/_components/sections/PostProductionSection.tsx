import type { AnalysisResultV2 } from "@/utils/analysis";
import { Badge, ChipList, Field, KeyValue, SectionCard } from "../ui";
import { formatSeconds, platformLabel } from "../format";

/** 后期制作：节奏、BGM、字幕、分平台标签与成片规格 */
export function PostProductionSection({ data }: { data: AnalysisResultV2 }) {
  const post = data.post_production;
  if (!post) return null;

  const adaptations = Object.entries(post.platform_adaptations ?? {});

  return (
    <SectionCard title="后期制作" description="节奏、音频、字幕与分平台发布建议">
      <div className="grid gap-6 md:grid-cols-2">
        {/* 节奏 */}
        {post.rhythm ? (
          <div>
            <div className="mb-2 text-xs font-medium text-muted-foreground">
              剪辑节奏
            </div>
            <dl className="divide-y divide-border">
              <KeyValue label="估算 BPM">
                <span className="font-numeric tabular-nums">
                  {post.rhythm.bpm_estimate?.toFixed(0) ?? "-"}
                </span>
              </KeyValue>
              <KeyValue label="剪切频率">
                <span className="font-numeric tabular-nums">
                  {post.rhythm.cut_frequency?.toFixed(1) ?? "-"}
                </span>
              </KeyValue>
              <KeyValue label="平均镜头时长">
                {formatSeconds(post.rhythm.avg_shot_duration)}
              </KeyValue>
              <KeyValue label="节奏模式">
                {post.rhythm.rhythm_pattern ?? "-"}
              </KeyValue>
              <KeyValue label="踩点评分">
                <span className="font-numeric tabular-nums">
                  {post.rhythm.beat_sync_score?.toFixed(1) ?? "-"}
                </span>
              </KeyValue>
            </dl>
          </div>
        ) : null}

        {/* BGM */}
        {post.bgm ? (
          <div>
            <div className="mb-2 text-xs font-medium text-muted-foreground">
              背景音乐
            </div>
            <dl className="divide-y divide-border">
              <KeyValue label="曲风">{post.bgm.genre ?? "-"}</KeyValue>
              <KeyValue label="情绪">{post.bgm.mood ?? "-"}</KeyValue>
              <KeyValue label="BPM">
                <span className="font-numeric tabular-nums">
                  {post.bgm.tempo_bpm?.toFixed(0) ?? "-"}
                </span>
              </KeyValue>
              <KeyValue label="Drop 时间点">
                {post.bgm.drop_timestamps?.length
                  ? post.bgm.drop_timestamps
                      .map((t) => formatSeconds(t))
                      .join(" / ")
                  : "-"}
              </KeyValue>
            </dl>
          </div>
        ) : null}
      </div>

      {/* 字幕 */}
      {post.subtitles?.length ? (
        <div className="mt-6 border-t border-border pt-4">
          <div className="mb-2 text-xs font-medium text-muted-foreground">
            字幕
          </div>
          <ul className="space-y-2">
            {post.subtitles.map((subtitle, index) => (
              <li
                key={index}
                className="flex flex-wrap items-center gap-2 rounded-md bg-muted px-3 py-2"
              >
                <span className="font-numeric text-xs text-muted-foreground tabular-nums">
                  {formatSeconds(subtitle.start_time)} –{" "}
                  {formatSeconds(subtitle.end_time)}
                </span>
                <span className="text-sm font-medium">{subtitle.text}</span>
                {subtitle.is_hook ? <Badge variant="gradient">钩子</Badge> : null}
                {subtitle.position ? (
                  <Badge variant="outline">{subtitle.position}</Badge>
                ) : null}
                {subtitle.style ? (
                  <span className="text-xs text-muted-foreground">
                    {subtitle.style}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* 分平台标签 */}
      {adaptations.length ? (
        <div className="mt-6 grid gap-4 border-t border-border pt-4 md:grid-cols-3">
          {adaptations.map(([platform, adaptation]) => (
            <Field key={platform} label={platformLabel(platform)}>
              <ChipList items={adaptation.recommended_hashtags ?? undefined} />
            </Field>
          ))}
        </div>
      ) : null}

      {/* 成片规格 */}
      {post.final_format ? (
        <div className="mt-6 border-t border-border pt-4">
          <dl className="grid gap-x-10 sm:grid-cols-2 lg:grid-cols-4">
            <KeyValue label="成片时长">
              {formatSeconds(post.final_format.duration)}
            </KeyValue>
            <KeyValue label="分辨率">
              <span className="font-numeric tabular-nums">
                {post.final_format.resolution ?? "-"}
              </span>
            </KeyValue>
            <KeyValue label="画幅">
              <span className="font-numeric tabular-nums">
                {post.final_format.aspect_ratio ?? "-"}
              </span>
            </KeyValue>
            <KeyValue label="封面帧">
              {formatSeconds(post.final_format.cover_frame_ts)}
            </KeyValue>
          </dl>
        </div>
      ) : null}
    </SectionCard>
  );
}
