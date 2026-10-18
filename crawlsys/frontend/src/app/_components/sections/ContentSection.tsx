import type { AnalysisResultV2 } from "@/utils/analysis";
import { Badge, ChipList, Field, KeyValue, SectionCard } from "../ui";
import { formatSeconds } from "../format";

/**
 * 内容画像：目标受众、创意概念、产品、场景、人物。
 */
export function ContentSection({ data }: { data: AnalysisResultV2 }) {
  const audience = data.target_definition?.target_audience;
  const target = data.target_definition;
  const creative = data.creative_concept;
  const product = data.product;
  const scene = data.scene;
  const person = data.person;

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        {/* 目标受众 */}
        {audience ? (
          <SectionCard
            title="目标受众"
            description={
              [
                target?.content_purpose && `目的：${target.content_purpose}`,
                target?.primary_kpi && `KPI：${target.primary_kpi}`,
              ]
                .filter(Boolean)
                .join(" · ") || undefined
            }
          >
            <dl className="divide-y divide-border">
              <KeyValue label="性别">{audience.gender ?? "-"}</KeyValue>
              <KeyValue label="年龄段">{audience.age_range ?? "-"}</KeyValue>
              <KeyValue label="价格敏感度">
                {audience.price_sensitivity ?? "-"}
              </KeyValue>
              <KeyValue label="目标时长">
                {formatSeconds(target?.video_length_target)}
              </KeyValue>
            </dl>
            <div className="mt-4 space-y-4 border-t border-border pt-4">
              {audience.style_preference?.length ? (
                <Field label="风格偏好">
                  <ChipList items={audience.style_preference} />
                </Field>
              ) : null}
              {audience.pain_points?.length ? (
                <Field label="痛点">
                  <ul className="list-disc space-y-1 pl-5">
                    {audience.pain_points.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </Field>
              ) : null}
              {audience.interests?.length ? (
                <Field label="兴趣标签">
                  <ChipList items={audience.interests} />
                </Field>
              ) : null}
              {target?.target_audience_profile ? (
                <Field label="受众画像">{target.target_audience_profile}</Field>
              ) : null}
              {target?.success_criteria ? (
                <Field label="成功标准">{target.success_criteria}</Field>
              ) : null}
            </div>
          </SectionCard>
        ) : null}

        {/* 创意概念 */}
        {creative ? (
          <SectionCard title="创意概念" description="选题、冲突与记忆点">
            <div className="grid gap-4">
              {creative.theme ? (
                <Field label="主题">{creative.theme}</Field>
              ) : null}
              {creative.conflict ? (
                <Field label="核心冲突">{creative.conflict}</Field>
              ) : null}
              {creative.hook_strategy ? (
                <Field label="钩子策略">{creative.hook_strategy}</Field>
              ) : null}
              {creative.memory_hook ? (
                <Field label="记忆点">{creative.memory_hook}</Field>
              ) : null}
              {creative.story_arc ? (
                <Field label="叙事弧线">{creative.story_arc}</Field>
              ) : null}
              {creative.creative_tags?.length ? (
                <Field label="创意标签">
                  <ChipList items={creative.creative_tags} />
                </Field>
              ) : null}
            </div>
          </SectionCard>
        ) : null}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* 产品 */}
        {product ? (
          <SectionCard title="产品" description={product.description ?? undefined}>
            <dl className="divide-y divide-border">
              <KeyValue label="品类">{product.category ?? "-"}</KeyValue>
              <KeyValue label="材质">{product.material ?? "-"}</KeyValue>
              <KeyValue label="面料厚度">
                {product.fabric_thickness ?? "-"}
              </KeyValue>
              <KeyValue label="弹性">{product.elasticity ?? "-"}</KeyValue>
              <KeyValue label="尺码建议">
                {product.size_recommendation ?? "-"}
              </KeyValue>
              <KeyValue label="价格带">{product.price_range ?? "-"}</KeyValue>
              <KeyValue label="适用季节">
                {product.suitable_season ?? "-"}
              </KeyValue>
            </dl>
            <div className="mt-4 space-y-4 border-t border-border pt-4">
              {product.display_actions?.length ? (
                <Field label="展示动作">
                  <ChipList items={product.display_actions} />
                </Field>
              ) : null}
              {product.suitable_scene?.length ? (
                <Field label="适用场景">
                  <ChipList items={product.suitable_scene} />
                </Field>
              ) : null}
              {product.craft_details?.length ? (
                <Field label="工艺细节">
                  <ul className="list-disc space-y-1 pl-5">
                    {product.craft_details.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </Field>
              ) : null}
              {product.color_options_visible?.length ? (
                <Field label="可见颜色">
                  <ChipList items={product.color_options_visible} />
                </Field>
              ) : null}
            </div>
          </SectionCard>
        ) : null}

        {/* 场景 */}
        {scene ? (
          <SectionCard title="场景与画面" description={scene.style_genre ?? undefined}>
            <div className="grid gap-4">
              {scene.background ? (
                <Field label="背景">{scene.background}</Field>
              ) : null}
              {scene.lighting ? (
                <Field label="光线">
                  {[
                    scene.lighting,
                    scene.light_temperature,
                    scene.light_contrast && `对比度 ${scene.light_contrast}`,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </Field>
              ) : null}
              {scene.composition ? (
                <Field label="构图">
                  {[scene.composition, scene.shot_size, scene.shooting_angle]
                    .filter(Boolean)
                    .join(" · ")}
                </Field>
              ) : null}
              {scene.camera ? (
                <Field label="相机">
                  {[scene.camera, scene.camera_movement]
                    .filter(Boolean)
                    .join(" · ")}
                </Field>
              ) : null}
              {scene.color_grading ? (
                <Field label="调色">{scene.color_grading}</Field>
              ) : null}
              {scene.style_keywords?.length ? (
                <Field label="风格关键词">
                  <ChipList items={scene.style_keywords} />
                </Field>
              ) : null}
              {scene.style_reference ? (
                <Field label="风格参考">{scene.style_reference}</Field>
              ) : null}
            </div>
          </SectionCard>
        ) : null}

        {/* 人物 */}
        {person ? (
          <SectionCard
            title="人物"
            description={person.body_type ?? undefined}
            extra={
              person.identity_consistency_risk ? (
                <Badge
                  variant={
                    person.identity_consistency_risk === "low"
                      ? "success"
                      : "warning"
                  }
                >
                  一致性风险 {person.identity_consistency_risk}
                </Badge>
              ) : null
            }
          >
            <div className="grid gap-4">
              {person.description ? (
                <Field label="形象">{person.description}</Field>
              ) : null}
              {person.clothing ? (
                <Field label="穿搭">{person.clothing}</Field>
              ) : null}
              {person.body_pose || person.gait_or_stance ? (
                <Field label="姿态">
                  {[person.body_pose, person.gait_or_stance]
                    .filter(Boolean)
                    .join(" · ")}
                </Field>
              ) : null}
              {person.gaze_direction ? (
                <Field label="视线方向">{person.gaze_direction}</Field>
              ) : null}
              {person.actions?.length ? (
                <Field label="动作序列">
                  <ol className="list-decimal space-y-1 pl-5">
                    {person.actions.map((action) => (
                      <li key={action}>{action}</li>
                    ))}
                  </ol>
                </Field>
              ) : null}
              {person.hand_actions?.length ? (
                <Field label="手部动作">
                  <ul className="list-disc space-y-1 pl-5">
                    {person.hand_actions.map((hand, index) => (
                      <li key={index}>
                        {hand.timestamp != null
                          ? `${formatSeconds(hand.timestamp)} `
                          : ""}
                        {hand.hand_position}
                        {hand.purpose ? `（${hand.purpose}）` : ""}
                      </li>
                    ))}
                  </ul>
                </Field>
              ) : null}
            </div>
          </SectionCard>
        ) : null}
      </div>
    </div>
  );
}
