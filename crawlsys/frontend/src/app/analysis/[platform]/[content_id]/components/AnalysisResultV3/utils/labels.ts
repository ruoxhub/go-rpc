import type { MessageKey } from "../../../../../../i18n";
import type {
  ActionPhaseV3,
  ContentTypeV3,
  DefectCategoryV3,
  EvidenceSourceV3,
  ExternalEvidenceStatusV3,
  GateStatusV3,
  InputModeV3,
  SystemDispositionV3,
  TopologyV3,
} from "../types";

export const gateKeys = {
  PASS: "analysis.v3.status.pass",
  BLOCK: "analysis.v3.status.block",
  INSUFFICIENT_EVIDENCE: "analysis.v3.status.insufficient",
} satisfies Record<GateStatusV3, MessageKey>;

export const dispositionKeys = {
  REJECT: "analysis.v3.disposition.reject",
  OWNER_REVIEW_REQUIRED: "analysis.v3.disposition.ownerReview",
} satisfies Record<SystemDispositionV3, MessageKey>;

export const inputModeKeys = {
  FULL_VIDEO: "analysis.v3.input.fullVideo",
  SAMPLED_FRAMES: "analysis.v3.input.sampledFrames",
} satisfies Record<InputModeV3, MessageKey>;

export const externalStatusKeys = {
  AVAILABLE: "analysis.v3.external.available",
  NOT_PROVIDED: "analysis.v3.external.notProvided",
  NOT_APPLICABLE: "analysis.v3.external.notApplicable",
} satisfies Record<ExternalEvidenceStatusV3, MessageKey>;

export const sourceKeys = {
  VIDEO: "analysis.v3.source.video",
  FRAME: "analysis.v3.source.frame",
  AUDIO: "analysis.v3.source.audio",
  TRANSCRIPT: "analysis.v3.source.transcript",
  TECHNICAL_METADATA: "analysis.v3.source.technicalMetadata",
  EXTERNAL: "analysis.v3.source.external",
} satisfies Record<EvidenceSourceV3, MessageKey>;

export const contentTypeKeys = {
  PRODUCT_DEMONSTRATION: "analysis.v3.type.productDemonstration",
  PROBLEM_SOLUTION: "analysis.v3.type.problemSolution",
  TESTIMONIAL: "analysis.v3.type.testimonial",
  COMPARISON: "analysis.v3.type.comparison",
  TUTORIAL: "analysis.v3.type.tutorial",
  LIFESTYLE: "analysis.v3.type.lifestyle",
  STORYTELLING: "analysis.v3.type.storytelling",
  OTHER: "analysis.v3.type.other",
} satisfies Record<ContentTypeV3, MessageKey>;

export const topologyKeys = {
  LINEAR: "analysis.v3.topology.linear",
  LOOP: "analysis.v3.topology.loop",
  MONTAGE: "analysis.v3.topology.montage",
  SPLIT_SCREEN: "analysis.v3.topology.splitScreen",
  ONE_TAKE: "analysis.v3.topology.oneTake",
  OTHER: "analysis.v3.topology.other",
} satisfies Record<TopologyV3, MessageKey>;

export const phaseKeys = {
  POSITIONING: "analysis.v3.phase.positioning",
  FORCE: "analysis.v3.phase.force",
  PEAK: "analysis.v3.phase.peak",
  FEEDBACK: "analysis.v3.phase.feedback",
  RELEASE: "analysis.v3.phase.release",
  RECOVERY: "analysis.v3.phase.recovery",
} satisfies Record<ActionPhaseV3, MessageKey>;

export const defectKeys = {
  PRODUCT: "analysis.v3.defect.product",
  PERSON: "analysis.v3.defect.person",
  PHYSICS: "analysis.v3.defect.physics",
  CAMERA: "analysis.v3.defect.camera",
  DELIVERY: "analysis.v3.defect.delivery",
  VISUAL_QUALITY: "analysis.v3.defect.visualQuality",
  AUDIO: "analysis.v3.defect.audio",
  OTHER: "analysis.v3.defect.other",
} satisfies Record<DefectCategoryV3, MessageKey>;

export const dimensionKeys: Partial<Record<string, MessageKey>> = {
  C1: "analysis.v3.dimension.c1", C2: "analysis.v3.dimension.c2", C3: "analysis.v3.dimension.c3", C4: "analysis.v3.dimension.c4",
  C5: "analysis.v3.dimension.c5", C6: "analysis.v3.dimension.c6", C7: "analysis.v3.dimension.c7", C8: "analysis.v3.dimension.c8",
  R1: "analysis.v3.dimension.r1", R2: "analysis.v3.dimension.r2", R3: "analysis.v3.dimension.r3", R4: "analysis.v3.dimension.r4", R5: "analysis.v3.dimension.r5", R6: "analysis.v3.dimension.r6",
  G1: "analysis.v3.dimension.g1", G2: "analysis.v3.dimension.g2", G3: "analysis.v3.dimension.g3", G4: "analysis.v3.dimension.g4", G5: "analysis.v3.dimension.g5", G6: "analysis.v3.dimension.g6", G7: "analysis.v3.dimension.g7",
};
