import { afterEach, describe, expect, it, vi } from "vitest";

import validV2Fixture from "./__fixtures__/analysis-v2.json";
import validV3Fixture from "./__fixtures__/analysis-v3.json";
import validV3CFixture from "./__fixtures__/analysis-v3-c.json";
import validV3GFixture from "./__fixtures__/analysis-v3-g.json";
import {
  classifyAnalysisResult,
  getAnalysisApiBaseUrl,
  getAnalysisThumbnailUrl,
  isAnalysisResultV2,
  isAnalysisResultV3,
} from "./analysis";

type PathPart = string | number;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function deepFreeze<T>(value: T): T {
  if (value && typeof value === "object") {
    Object.freeze(value);
    Object.values(value).forEach(deepFreeze);
  }
  return value;
}

function cloneAndSet(source: unknown, path: PathPart[], replacement: unknown) {
  const clone: unknown = structuredClone(source);
  let cursor = clone;

  for (const part of path.slice(0, -1)) {
    if (typeof part === "number") {
      if (!Array.isArray(cursor)) throw new Error("fixture path is not an array");
      cursor = cursor[part];
    } else {
      if (!isRecord(cursor)) throw new Error("fixture path is not an object");
      cursor = cursor[part];
    }
  }

  const last = path.at(-1);
  if (typeof last === "number") {
    if (!Array.isArray(cursor)) throw new Error("fixture target is not an array");
    cursor[last] = replacement;
  } else if (typeof last === "string") {
    if (!isRecord(cursor)) throw new Error("fixture target is not an object");
    cursor[last] = replacement;
  } else {
    throw new Error("fixture mutation path cannot be empty");
  }
  return clone;
}

const validV2 = deepFreeze({
  meta: { schema_version: "v2.0", confidence_overall: 0.8 },
  target_definition: {
    platform_tone_match: 8,
    target_audience: { pain_points: ["fit"], interests: ["sports"] },
  },
  person: { actions: ["walk"], hand_actions: [{ timestamp: 1, hand_position: "front" }] },
  product: { display_actions: ["stretch"], craft_details: ["seam"] },
  timeline: [{ start_time: 0, end_time: 1, emotion_intensity: 0.7 }],
  conversion_points: [{ timestamp: 1, description: "cta", confidence: 0.8 }],
  viral_points: [{ timestamp: 1, description: "hook", confidence: 0.8 }],
  selling_points: [{ description: "fit", confidence: 0.8 }],
  emotion_arc: { intensity_curve: [{ timestamp: 1, intensity: 0.8, trigger: "cta" }] },
  ai_video_prompt: { key_frames: [{ timestamp: 1, description: "frame" }] },
  iteration: { issues: [{ severity: "minor", description: "shake" }] },
  post_production: {
    subtitles: [{ start_time: 0, end_time: 1, text: "hello" }],
    platform_adaptations: { tiktok: { recommended_hashtags: ["demo"] } },
  },
  scoring: { overall: { score: 8.6, reason: "clear" }, hook: { score: 8 } },
});

const legacyV2 = deepFreeze({
  scoring: { overall: { score: 7.5 } },
});

const nullableScoreLegacyV2 = deepFreeze({
  scoring: { overall: { score: null, reason: null } },
});

const nullableRootArraysV2 = deepFreeze({
  scoring: { overall: { score: 6, reason: null } },
  timeline: null,
  conversion_points: null,
  viral_points: null,
  selling_points: null,
});

const backendV2: unknown = deepFreeze(structuredClone(validV2Fixture));

// Generated from backend AnalysisResultV3.model_dump(mode="json") with:
// rtk python <fixture generator recorded in task-9-report.md>
const validV3: unknown = deepFreeze(structuredClone(validV3Fixture));
const validV3C: unknown = deepFreeze(structuredClone(validV3CFixture));
const validV3G: unknown = deepFreeze(structuredClone(validV3GFixture));

describe("analysis result v2 guard", () => {
  it("accepts explicit and versionless legacy v2 results", () => {
    expect(isAnalysisResultV2(validV2)).toBe(true);
    expect(isAnalysisResultV2(legacyV2)).toBe(true);
    expect(isAnalysisResultV2(nullableScoreLegacyV2)).toBe(true);
    expect(isAnalysisResultV2(nullableRootArraysV2)).toBe(true);
    expect(isAnalysisResultV3(validV2)).toBe(false);
  });

  it("accepts the backend v2 default model_dump and classifies it as v2", () => {
    expect(isAnalysisResultV2(backendV2)).toBe(true);
    expect(classifyAnalysisResult(backendV2).version).toBe("v2");
  });

  it.each([
    ["timeline item", ["timeline", 0], null],
    ["conversion item", ["conversion_points", 0], null],
    ["viral item", ["viral_points", 0], null],
    ["selling item", ["selling_points", 0], null],
    ["hand action", ["person", "hand_actions", 0], null],
    ["emotion point", ["emotion_arc", "intensity_curve", 0], null],
    ["key frame", ["ai_video_prompt", "key_frames", 0], null],
    ["iteration issue", ["iteration", "issues", 0], null],
    ["subtitle", ["post_production", "subtitles", 0], null],
    ["platform adaptation", ["post_production", "platform_adaptations", "tiktok"], null],
    ["non-finite score", ["scoring", "hook", "score"], Number.POSITIVE_INFINITY],
    ["boolean score", ["scoring", "hook", "score"], true],
    ["object reason", ["scoring", "overall", "reason"], {}],
  ] satisfies [string, PathPart[], unknown][]) (
    "rejects malformed legacy %s",
    (_label, path, replacement) => {
      expect(isAnalysisResultV2(cloneAndSet(validV2, path, replacement))).toBe(false);
    },
  );
});

describe("analysis result v3 guard", () => {
  it("accepts an immutable non-empty backend model_dump fixture", () => {
    expect(isAnalysisResultV3(validV3)).toBe(true);
    expect(isAnalysisResultV2(validV3)).toBe(false);
    expect(Object.isFrozen(validV3)).toBe(true);
  });

  it.each([
    ["C-only", validV3C],
    ["R", validV3],
    ["G", validV3G],
  ])("accepts and classifies a backend %s route fixture", (_route, fixture) => {
    expect(isAnalysisResultV3(fixture)).toBe(true);
    expect(classifyAnalysisResult(fixture).version).toBe("v3");
  });

  it("keeps R4 and G1 gated and explains unavailable G1 product evidence", () => {
    const classifiedR = classifyAnalysisResult(validV3);
    const classifiedG = classifyAnalysisResult(validV3G);
    expect(classifiedR.version).toBe("v3");
    expect(classifiedG.version).toBe("v3");
    if (classifiedR.version !== "v3" || classifiedG.version !== "v3") return;

    const r4 = classifiedR.result.evaluation.specialized_score_r?.dimensions.find(
      (dimension) => dimension.dimension_id === "R4",
    );
    const g1 = classifiedG.result.evaluation.specialized_score_g?.dimensions.find(
      (dimension) => dimension.dimension_id === "G1",
    );

    expect(r4).toMatchObject({ scorable: false, awarded_points: null });
    expect(g1).toMatchObject({ scorable: false, awarded_points: null });
    expect(g1?.unscorable_reason?.trim()).toBeTruthy();
  });

  it.each([
    ["timeline null item", ["observation", "timeline", 0], null],
    ["dimension null item", ["evaluation", "common_score_c", "dimensions", 0], null],
    ["string diagnostic total", ["evaluation", "diagnostic_total"], "42"],
    ["numeric specialized section", ["evaluation", "specialized_score_r"], 42],
    ["timings leaf", ["meta", "timings", "observation_attempts"], "1"],
    ["technical metadata leaf", ["evidence_card", "technical_metadata", "width"], "1080"],
    ["external evidence enum", ["evidence_card", "product_reference", "status"], "UNKNOWN"],
    ["coverage item", ["evidence_card", "coverage_limitations", 0], null],
    ["limitation item", ["evidence_card", "limitations", 0], null],
    ["classification enum", ["content_classification", "primary_type"], "UNKNOWN"],
    ["action phase enum", ["observation", "timeline", 0, "action_phases", 0], "UNKNOWN"],
    ["timeline reference", ["observation", "timeline", 0, "evidence_sources", 0], null],
    ["reference source enum", ["observation", "timeline", 0, "evidence_sources", 0, "source"], "UNKNOWN"],
    ["provable claim leaf", ["observation", "timeline", 0, "provable_claims", 0], 1],
    ["timeline defect enum", ["observation", "timeline", 0, "defects", 0], "UNKNOWN"],
    ["business answer leaf", ["observation", "business_logic", "visible_proof"], {}],
    ["g0 finding", ["evaluation", "g0_assessment", "findings", 0], null],
    ["review route", ["evaluation", "review_route"], "C"],
    ["specialized dimension", ["evaluation", "specialized_score_r", "dimensions", 0], null],
    ["dimension evidence", ["evaluation", "common_score_c", "dimensions", 0, "evidence_timestamps"], [null]],
    ["dimension score leaf", ["evaluation", "common_score_c", "dimensions", 0, "awarded_points"], "0"],
    ["partial points", ["evaluation", "partial_points"], "0"],
    ["conflict item", ["evaluation", "evidence_conflicts", 0], null],
    ["supplemental item", ["evaluation", "supplemental_evidence", 0], null],
    ["supplemental affected dimension", ["evaluation", "supplemental_evidence", 0, "affected_dimension_ids", 0], 2],
    ["unscorable reason", ["evaluation", "common_score_c", "dimensions", 0, "unscorable_reason"], {}],
    ["decision gate", ["decision", "gate_status"], "UNKNOWN"],
    ["decision scoring", ["decision", "scoring_status"], "UNKNOWN"],
    ["decision owner action", ["decision", "system_disposition"], "UNKNOWN"],
    ["formal grade", ["decision", "formal_grade"], "P1"],
  ] satisfies [string, PathPart[], unknown][]) (
    "rejects malformed v3 %s",
    (_label, path, replacement) => {
      expect(isAnalysisResultV3(cloneAndSet(validV3, path, replacement))).toBe(false);
    },
  );

  it("accepts the nullable diagnostic total wire value", () => {
    expect(
      isAnalysisResultV3(
        cloneAndSet(validV3, ["evaluation", "diagnostic_total"], null),
      ),
    ).toBe(true);
  });
});

describe("classifyAnalysisResult", () => {
  it.each([
    ["v3", validV3, "v3"],
    ["v2", validV2, "v2"],
    ["missing", undefined, "unavailable"],
    ["unknown", { meta: { schema_version: "v4.0" } }, "unavailable"],
  ])("routes %s results", (_label, value, expectedVersion) => {
    expect(classifyAnalysisResult(value).version).toBe(expectedVersion);
  });
});

describe("getAnalysisApiBaseUrl", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("浏览器使用同源 analysis 路径", () => {
    vi.stubGlobal("window", {});
    expect(getAnalysisApiBaseUrl()).toBe("/api/analysis");
  });

  it("服务端使用环境变量并移除末尾斜杠", () => {
    vi.stubEnv("ANALYSIS_API_BASE_URL", "http://backend:8081/api/analysis///");
    expect(getAnalysisApiBaseUrl()).toBe("http://backend:8081/api/analysis");
  });

  it("服务端渲染的缩略图仍使用浏览器同源路径", () => {
    vi.stubGlobal("window", undefined);
    vi.stubEnv("ANALYSIS_API_BASE_URL", "http://backend:8081/api/analysis");

    expect(getAnalysisThumbnailUrl("tik tok", "video/1")).toBe(
      "/api/analysis/tik%20tok/video%2F1/thumbnail",
    );
  });
});
