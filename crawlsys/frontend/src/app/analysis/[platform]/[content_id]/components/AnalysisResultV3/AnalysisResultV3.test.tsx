// @vitest-environment jsdom

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import rFixture from "../../../../../../utils/__fixtures__/analysis-v3.json";
import cFixture from "../../../../../../utils/__fixtures__/analysis-v3-c.json";
import gFixture from "../../../../../../utils/__fixtures__/analysis-v3-g.json";
import {
  classifyAnalysisResult,
  type AnalysisResultV3 as AnalysisResultV3Data,
} from "../../../../../../utils/analysis";

import { AnalysisResultV3 } from ".";

afterEach(cleanup);

function fixtureResult(fixture: unknown): AnalysisResultV3Data {
  const classified = classifyAnalysisResult(fixture);
  if (classified.version !== "v3") {
    throw new Error("Expected a valid v3 fixture");
  }
  return structuredClone(classified.result);
}

describe("AnalysisResultV3", () => {
  it("renders the decision before scores and exposes the complete R-route evidence review", () => {
    const result = fixtureResult(rFixture);
    result.observation.timeline[0].action_phases = [
      "POSITIONING",
      "FORCE",
      "PEAK",
      "FEEDBACK",
      "RELEASE",
      "RECOVERY",
    ];
    const { container } = render(<AnalysisResultV3 result={result} />);

    const decision = screen.getByRole("heading", { name: "评审决策" });
    const scoring = screen.getByRole("heading", { name: "暂定诊断评分" });
    expect(
      decision.compareDocumentPosition(scoring) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).not.toBe(0);

    const evidence = screen.getByRole("region", { name: "证据卡" });
    expect(within(evidence).getByText("fixture-video")).not.toBeNull();
    expect(within(evidence).getByText("完整视频")).not.toBeNull();
    expect(within(evidence).getByText("[1.00s, 2.00s]")).not.toBeNull();
    expect(within(evidence).getByText("ending not sampled")).not.toBeNull();
    expect(within(evidence).getByText("1.00s")).not.toBeNull();
    expect(within(evidence).getByText("performance metrics")).not.toBeNull();
    expect(within(evidence).getByText("no metrics")).not.toBeNull();
    expect(within(evidence).getAllByText("未提供").length).toBeGreaterThan(0);

    const classification = screen.getByRole("region", { name: "内容分类" });
    expect(within(classification).getByText("商品演示")).not.toBeNull();
    expect(within(classification).getByText("教程")).not.toBeNull();
    expect(within(classification).getByText("线性结构")).not.toBeNull();
    expect(within(classification).getByText("R 路线")).not.toBeNull();

    const scoreRegion = screen.getByRole("region", { name: "暂定诊断评分" });
    expect(within(scoreRegion).getByText("G0 硬失败检查")).not.toBeNull();
    expect(within(scoreRegion).getByText("C 公共商业创意分")).not.toBeNull();
    expect(within(scoreRegion).getByText("R 参考视频价值分")).not.toBeNull();
    expect(within(scoreRegion).queryByText("G 生成视频执行分")).toBeNull();
    expect(within(scoreRegion).getByText("42.0")).not.toBeNull();
    expect(within(scoreRegion).getAllByText("暂定").length).toBeGreaterThan(0);
    expect(within(scoreRegion).getAllByText("不可评分原因未提供").length).toBeGreaterThan(0);

    const timeline = screen.getByRole("region", { name: "观察时间线" });
    for (const phase of ["定位", "施力", "峰值", "反馈", "释放", "恢复"]) {
      expect(within(timeline).getByText(phase)).not.toBeNull();
    }
    expect(within(timeline).getAllByText(/视频.*1\.25s/).length).toBeGreaterThan(0);
    expect(within(timeline).getByText("flexible")).not.toBeNull();
    expect(within(timeline).getByText("bend is visible")).not.toBeNull();
    expect(within(timeline).getByText("minor shake")).not.toBeNull();

    const review = screen.getByRole("region", { name: "补充评审证据" });
    expect(within(review).getByText("audio cue")).not.toBeNull();
    expect(within(review).getByText("product visible")).not.toBeNull();
    expect(within(review).getByText("proof incomplete")).not.toBeNull();
    expect(within(review).getByText("需负责人复核")).not.toBeNull();
    expect(within(review).getByText("organic reach unknown")).not.toBeNull();

    expect(container.textContent).not.toContain("AI 视频生成提示词");
    expect(container.textContent).not.toContain("迭代验证");
    expect(container.textContent).not.toContain("后期制作");
    expect(container.textContent).not.toContain("正式评级");
  });

  it("keeps BLOCK semantically dominant even when the diagnostic total is high", () => {
    const result = fixtureResult(rFixture);
    result.decision.gate_status = "BLOCK";
    result.decision.system_disposition = "REJECT";
    result.decision.reasons = ["critical product drift"];
    result.evaluation.diagnostic_total = 99.9;

    render(<AnalysisResultV3 result={result} />);

    const banner = screen.getByRole("alert");
    expect(within(banner).getByText("阻断")).not.toBeNull();
    expect(within(banner).getByText("拒绝")).not.toBeNull();
    expect(within(banner).getByText("critical product drift")).not.toBeNull();
    expect(screen.getByText("99.9")).not.toBeNull();
    expect(screen.queryByText("通过")).toBeNull();
  });

  it("renders only the selected G section and names the unavailable reason", () => {
    render(<AnalysisResultV3 result={fixtureResult(gFixture)} />);

    expect(screen.getByText("G 路线")).not.toBeNull();
    expect(screen.getByText("G 生成视频执行分")).not.toBeNull();
    expect(screen.queryByText("R 参考视频价值分")).toBeNull();
    expect(screen.getByText("Missing product reference evidence")).not.toBeNull();
    expect(screen.getAllByText("不可用").length).toBeGreaterThan(0);
  });

  it("renders an explicit C-only route without either specialized score", () => {
    render(<AnalysisResultV3 result={fixtureResult(cFixture)} />);

    expect(screen.getByText("仅 C 路线")).not.toBeNull();
    expect(screen.getByText("C 公共商业创意分")).not.toBeNull();
    expect(screen.queryByText("R 参考视频价值分")).toBeNull();
    expect(screen.queryByText("G 生成视频执行分")).toBeNull();
  });

  it("renders translated empty states for empty arrays and nullable values", () => {
    const result = fixtureResult(gFixture);
    result.content_classification.secondary_types = [];
    result.content_classification.evidence_timecodes = [];
    result.evidence_card.sampled_timestamps = [];
    result.evidence_card.observed_ranges = [];
    result.evidence_card.unobserved_ranges = [];
    result.evidence_card.coverage_limitations = [];
    result.evidence_card.missing_evidence = [];
    result.evidence_card.limitations = [];
    result.observation.timeline = [];
    result.observation.claim_evidence_chains = [];
    result.observation.defects = [];
    result.evaluation.supplemental_evidence = [];
    result.evaluation.evidence_conflicts = [];
    result.evaluation.diagnostic_total = null;

    render(<AnalysisResultV3 result={result} />);

    expect(screen.getAllByText("暂无数据").length).toBeGreaterThan(0);
    expect(screen.getAllByText("未提供").length).toBeGreaterThan(0);
    expect(screen.getAllByText("不可用").length).toBeGreaterThan(0);
  });

  it("does not expose local paths or API-key-shaped source identifiers", () => {
    const result = fixtureResult(rFixture);
    result.evidence_card.source_id = "C:\\private\\video.mp4";
    result.evidence_card.source_sha256 = "sk-super-secret-value";

    const { container } = render(<AnalysisResultV3 result={result} />);

    expect(screen.getAllByText("敏感标识已隐藏")).toHaveLength(2);
    expect(container.textContent).not.toContain("C:\\private");
    expect(container.textContent).not.toContain("sk-super-secret-value");
  });
});
