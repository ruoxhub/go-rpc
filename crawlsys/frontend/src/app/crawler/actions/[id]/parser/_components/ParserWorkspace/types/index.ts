import type {
  JsonValue,
  ParserCapabilities,
  ParserDefinition,
  ParserOutput,
  ParserPreviewReport,
  ParserRevision,
  ParserSample,
  ParserSampleDetail,
} from "@/api/action-parser/action-parser.types";
import type {
  ActionSchemaResponse,
  LlmModelOption,
} from "@/api/task-metadata/task-metadata.types";
import type { Action } from "@/utils/crawler/crawler-types";

export interface ParserWorkspaceState {
  action: Action;
  platformName: string;
  capabilities: ParserCapabilities;
  actionSchema: ActionSchemaResponse["schema"];
  llmModels: LlmModelOption[];
  samples: ParserSample[];
  sampleServerCount: number;
  samplesExhausted: boolean;
  revisions: ParserRevision[];
  revisionServerCount: number;
  revisionsExhausted: boolean;
  draft: ParserRevision | null;
  published: ParserRevision | null;
  baseDefinition: ParserDefinition | null;
  workingDefinition: ParserDefinition | null;
  dirty: boolean;
  conflicted: boolean;
  activeSampleId: number | null;
  sampleDetails: Record<number, ParserSampleDetail>;
  selectedSampleIds: number[];
  previewReport: ParserPreviewReport | null;
  aiCandidate: ParserDefinition | null;
  aiPreview: JsonValue[] | null;
  aiReceipt: string | null;
  pendingOutput: ParserOutput;
  activePointerTarget:
    | { kind: "record_path" }
    | { kind: "source"; fieldIndex: number }
    | null;
  definitionView: "structured" | "json";
  expandedFieldIndex: number | null;
  activeSection: "workspace" | "samples" | "history";
}

export type ParserWorkspaceServerState = Pick<
  ParserWorkspaceState,
  | "action"
  | "platformName"
  | "capabilities"
  | "actionSchema"
  | "llmModels"
  | "samples"
  | "sampleServerCount"
  | "samplesExhausted"
  | "revisions"
  | "revisionServerCount"
  | "revisionsExhausted"
  | "draft"
  | "published"
>;

export function createInitialWorkspaceState(
  server: ParserWorkspaceServerState,
): ParserWorkspaceState {
  return {
    ...server,
    baseDefinition: server.draft?.definition ?? null,
    workingDefinition: server.draft?.definition ?? null,
    dirty: false,
    conflicted: false,
    activeSampleId: null,
    sampleDetails: {},
    selectedSampleIds: [],
    previewReport: server.draft?.validation_report ?? null,
    aiCandidate: null,
    aiPreview: null,
    aiReceipt: null,
    pendingOutput: server.draft?.definition.output ?? { mode: "json" },
    activePointerTarget: null,
    definitionView: "structured",
    expandedFieldIndex: null,
    activeSection: "workspace",
  };
}
