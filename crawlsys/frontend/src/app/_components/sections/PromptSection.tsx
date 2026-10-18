import type { AnalysisResultV2 } from "@/utils/analysis";
import { CopyButton } from "../CopyButton";
import { Badge, ChipList, Field, SectionCard } from "../ui";
import { formatSeconds, severityMeta } from "../format";

/** AI 视频生成提示词 + 迭代验证结果 */
export function PromptSection({ data }: { data: AnalysisResultV2 }) {
  const prompt = data.ai_video_prompt;
  const iteration = data.iteration;
  if (!prompt && !iteration) return null;

  const params = Object.entries(prompt?.recommended_params ?? {}).filter(
    ([, value]) => value != null,
  );

  return (
    <div className="space-y-6">
      {prompt ? (
        <SectionCard
          title="AI 视频生成提示词"
          description={
            prompt.recommended_model
              ? `推荐模型：${prompt.recommended_model}`
              : undefined
          }
          extra={<CopyButton text={prompt.full_prompt_en ?? undefined} label="复制英文提示词" />}
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <PromptBlock
              label="完整提示词（中文）"
              text={prompt.full_prompt_zh ?? undefined}
            />
            <PromptBlock
              label="完整提示词（英文）"
              text={prompt.full_prompt_en ?? undefined}
            />
          </div>

          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {prompt.subject_prompt ? (
              <Field label="主体">{prompt.subject_prompt}</Field>
            ) : null}
            {prompt.scene_prompt ? (
              <Field label="场景">{prompt.scene_prompt}</Field>
            ) : null}
            {prompt.action_prompt ? (
              <Field label="动作">{prompt.action_prompt}</Field>
            ) : null}
            {prompt.style_prompt ? (
              <Field label="风格">{prompt.style_prompt}</Field>
            ) : null}
          </div>

          {prompt.negative_prompt ? (
            <div className="mt-4">
              <PromptBlock label="负面提示词" text={prompt.negative_prompt} />
            </div>
          ) : null}

          {prompt.key_frames?.length ? (
            <div className="mt-6">
              <div className="mb-2 text-xs font-medium text-muted-foreground">
                关键帧提示词
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                {prompt.key_frames.map((frame, index) => (
                  <div
                    key={index}
                    className="rounded-md border border-border p-4"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <Badge variant="muted">{frame.position ?? "-"}</Badge>
                      {frame.timestamp != null ? (
                        <span className="font-numeric text-xs text-muted-foreground tabular-nums">
                          {formatSeconds(frame.timestamp)}
                        </span>
                      ) : null}
                    </div>
                    {frame.description ? (
                      <p className="mt-2 text-xs leading-5 text-muted-foreground">
                        {frame.description}
                      </p>
                    ) : null}
                    {frame.prompt_text ? (
                      <p className="mt-2 text-sm leading-6">
                        {frame.prompt_text}
                      </p>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="mt-6 grid gap-4 border-t border-border pt-4 md:grid-cols-2">
            {params.length ? (
              <Field label="推荐参数">
                <div className="flex flex-wrap gap-1.5">
                  {params.map(([key, value]) => (
                    <span
                      key={key}
                      className="inline-flex items-center rounded-md bg-muted px-2 py-1 text-xs leading-4"
                    >
                      {key}=
                      <span className="font-numeric tabular-nums">
                        {String(value)}
                      </span>
                    </span>
                  ))}
                </div>
              </Field>
            ) : null}
            {prompt.style_anchors?.length ? (
              <Field label="风格锚点">
                <ChipList items={prompt.style_anchors} />
              </Field>
            ) : null}
            {prompt.consistency_constraints?.length ? (
              <Field label="一致性约束">
                <ul className="list-disc space-y-1 pl-5">
                  {prompt.consistency_constraints.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </Field>
            ) : null}
          </div>
        </SectionCard>
      ) : null}

      {iteration ? (
        <SectionCard
          title="迭代验证"
          description={
            iteration.verification_target
              ? `验证目标：${iteration.verification_target}`
              : undefined
          }
          extra={
            <div className="flex items-center gap-2">
              {iteration.round_number != null ? (
                <Badge variant="outline">第 {iteration.round_number} 轮</Badge>
              ) : null}
              {iteration.passed != null ? (
                <Badge variant={iteration.passed ? "success" : "destructive"}>
                  {iteration.passed ? "已通过" : "未通过"}
                </Badge>
              ) : null}
            </div>
          }
        >
          {iteration.issues?.length ? (
            <ul className="space-y-4">
              {iteration.issues.map((issue, index) => {
                const severity = severityMeta(issue.severity ?? undefined);
                return (
                  <li
                    key={index}
                    className="rounded-md border border-border p-4"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      {issue.category ? (
                        <Badge variant="muted">{issue.category}</Badge>
                      ) : null}
                      <Badge variant={severity.variant}>{severity.label}</Badge>
                      {issue.timestamp_start != null ? (
                        <span className="font-numeric text-xs text-muted-foreground tabular-nums">
                          {formatSeconds(issue.timestamp_start)} –{" "}
                          {formatSeconds(issue.timestamp_end)}
                        </span>
                      ) : null}
                    </div>
                    {issue.description ? (
                      <p className="mt-2 text-sm leading-6">
                        {issue.description}
                      </p>
                    ) : null}
                    {issue.suggested_fix ? (
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        修复建议：{issue.suggested_fix}
                      </p>
                    ) : null}
                    {issue.revised_prompt_snippet ? (
                      <code className="mt-2 block rounded-md bg-muted px-3 py-2 text-xs leading-5">
                        {issue.revised_prompt_snippet}
                      </code>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          ) : null}

          {iteration.revised_prompt ? (
            <div className="mt-4">
              <PromptBlock
                label={`修订后提示词${iteration.revision_focus ? `（${iteration.revision_focus}）` : ""}`}
                text={iteration.revised_prompt}
              />
            </div>
          ) : null}
        </SectionCard>
      ) : null}
    </div>
  );
}

/** 提示词文本块：标签 + 复制按钮 + 文本 */
function PromptBlock({ label, text }: { label: string; text?: string }) {
  if (!text) return null;
  return (
    <div className="rounded-md border border-border p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">
          {label}
        </span>
        <CopyButton text={text} />
      </div>
      <p className="whitespace-pre-wrap text-sm leading-6">{text}</p>
    </div>
  );
}
