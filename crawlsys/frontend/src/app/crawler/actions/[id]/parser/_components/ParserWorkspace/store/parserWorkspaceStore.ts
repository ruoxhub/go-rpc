import { combine } from "zustand/middleware";
import { createStore } from "zustand/vanilla";

import type {
  ParserAssistResult,
  ParserDefinition,
  ParserOutput,
  ParserPreviewReport,
  ParserRevision,
  ParserSample,
  ParserSampleDetail,
} from "@/api/action-parser/action-parser.types";

import type { ParserWorkspaceState } from "../types";
import { definitionsEqual } from "../utils/definition";

export interface ParserWorkspaceActions {
  updateDefinition(definition: ParserDefinition): void;
  applySavedRevision(revision: ParserRevision): void;
  applyAiCandidate(result: ParserAssistResult): void;
  acceptAiCandidate(): void;
  clearAiCandidate(): void;
  setPendingOutput(output: ParserOutput): void;
  markConflict(): void;
  clearConflict(): void;
  prependSample(sample: ParserSample): void;
  appendSamples(
    items: ParserSample[],
    serverCount: number,
    exhausted: boolean,
  ): void;
  replaceSamplesFromServer(items: ParserSample[]): void;
  removeSample(sampleId: number): void;
  setSampleDetail(detail: ParserSampleDetail): void;
  setActiveSample(sampleId: number | null): void;
  toggleSelectedSample(sampleId: number): void;
  applyPreviewReport(report: ParserPreviewReport): void;
  prependRevision(revision: ParserRevision): void;
  appendRevisions(
    items: ParserRevision[],
    serverCount: number,
    exhausted: boolean,
  ): void;
  replaceRevisionsFromServer(items: ParserRevision[]): void;
  discardLocalAndReplaceRevisions(items: ParserRevision[]): void;
  replaceRevision(revision: ParserRevision): void;
  removeRevision(revisionId: number): void;
  setActivePointerTarget(
    target: ParserWorkspaceState["activePointerTarget"],
  ): void;
  setDefinitionView(view: ParserWorkspaceState["definitionView"]): void;
  setExpandedFieldIndex(index: number | null): void;
  setActiveSection(section: ParserWorkspaceState["activeSection"]): void;
}

function prependById<T, K extends keyof T>(items: T[], item: T, key: K) {
  return [item, ...items.filter((current) => current[key] !== item[key])];
}

function appendUniqueById<T, K extends keyof T>(
  items: T[],
  added: T[],
  key: K,
) {
  const seen = new Set(items.map((item) => item[key]));
  const unique = added.filter((item) => {
    if (seen.has(item[key])) return false;
    seen.add(item[key]);
    return true;
  });
  return [...items, ...unique];
}

function isDirty(
  base: ParserDefinition | null,
  working: ParserDefinition | null,
) {
  if (base === null || working === null) return base !== working;
  return !definitionsEqual(base, working);
}

export function createParserWorkspaceStore(initialState: ParserWorkspaceState) {
  return createStore(
    combine(
      {
        ...initialState,
        dirty: isDirty(
          initialState.baseDefinition,
          initialState.workingDefinition,
        ),
      },
      (set): ParserWorkspaceActions => ({
        updateDefinition: (definition) =>
          set((state) =>
            state.workingDefinition !== null &&
            definitionsEqual(state.workingDefinition, definition)
              ? {}
              : {
                  workingDefinition: definition,
                  dirty: isDirty(state.baseDefinition, definition),
                  aiCandidate: null,
                  aiPreview: null,
                  aiReceipt: null,
                },
          ),
        applySavedRevision: (revision) =>
          set((state) => ({
            draft: revision,
            revisions: prependById(state.revisions, revision, "revision_id"),
            baseDefinition: revision.definition,
            workingDefinition: revision.definition,
            pendingOutput: revision.definition.output,
            dirty: false,
            conflicted: false,
            previewReport: null,
            aiCandidate: null,
            aiPreview: null,
            aiReceipt: null,
          })),
        applyAiCandidate: (result) =>
          set({
            aiCandidate: result.definition,
            aiPreview: result.preview,
            aiReceipt: result.assistReceipt,
          }),
        acceptAiCandidate: () =>
          set((state) =>
            state.aiCandidate === null
              ? {}
              : {
                  workingDefinition: state.aiCandidate,
                  pendingOutput: state.aiCandidate.output,
                  dirty: isDirty(state.baseDefinition, state.aiCandidate),
                  aiCandidate: null,
                },
          ),
        clearAiCandidate: () =>
          set({ aiCandidate: null, aiPreview: null, aiReceipt: null }),
        setPendingOutput: (pendingOutput) => set({ pendingOutput }),
        markConflict: () => set({ conflicted: true }),
        clearConflict: () => set({ conflicted: false }),
        prependSample: (sample) =>
          set((state) => ({
            samples: prependById(state.samples, sample, "sample_id"),
            activeSampleId: sample.sample_id,
            selectedSampleIds: state.selectedSampleIds.includes(
              sample.sample_id,
            )
              ? state.selectedSampleIds
              : [...state.selectedSampleIds, sample.sample_id].slice(-50),
          })),
        appendSamples: (items, serverCount, exhausted) =>
          set((state) => ({
            samples: appendUniqueById(state.samples, items, "sample_id"),
            sampleServerCount: serverCount,
            samplesExhausted: exhausted,
          })),
        replaceSamplesFromServer: (items) =>
          set((state) => {
            const ids = new Set(items.map((item) => item.sample_id));
            const sampleDetails: Record<number, ParserSampleDetail> = {};
            for (const [id, detail] of Object.entries(state.sampleDetails)) {
              if (ids.has(Number(id))) sampleDetails[Number(id)] = detail;
            }
            return {
              samples: items,
              sampleServerCount: items.length,
              samplesExhausted: items.length < 20,
              activeSampleId:
                state.activeSampleId !== null && ids.has(state.activeSampleId)
                  ? state.activeSampleId
                  : null,
              selectedSampleIds: state.selectedSampleIds.filter((id) =>
                ids.has(id),
              ),
              sampleDetails,
            };
          }),
        removeSample: (sampleId) =>
          set((state) => {
            const sampleDetails = { ...state.sampleDetails };
            delete sampleDetails[sampleId];
            return {
              samples: state.samples.filter(
                (item) => item.sample_id !== sampleId,
              ),
              activeSampleId:
                state.activeSampleId === sampleId
                  ? null
                  : state.activeSampleId,
              selectedSampleIds: state.selectedSampleIds.filter(
                (item) => item !== sampleId,
              ),
              sampleDetails,
            };
          }),
        setSampleDetail: (detail) =>
          set((state) => ({
            sampleDetails: {
              ...state.sampleDetails,
              [detail.sample_id]: detail,
            },
          })),
        setActiveSample: (sampleId) => set({ activeSampleId: sampleId }),
        toggleSelectedSample: (sampleId) =>
          set((state) => ({
            selectedSampleIds: state.selectedSampleIds.includes(sampleId)
              ? state.selectedSampleIds.filter((item) => item !== sampleId)
              : state.selectedSampleIds.length < 50
                ? [...state.selectedSampleIds, sampleId]
                : state.selectedSampleIds,
          })),
        applyPreviewReport: (report) =>
          set((state) => {
            const draft =
              state.draft === null
                ? null
                : { ...state.draft, validation_report: report };
            return {
              previewReport: report,
              draft,
              revisions:
                draft === null
                  ? state.revisions
                  : prependById(state.revisions, draft, "revision_id"),
            };
          }),
        prependRevision: (revision) =>
          set((state) => ({
            revisions: prependById(state.revisions, revision, "revision_id"),
          })),
        appendRevisions: (items, serverCount, exhausted) =>
          set((state) => ({
            revisions: appendUniqueById(
              state.revisions,
              items,
              "revision_id",
            ),
            revisionServerCount: serverCount,
            revisionsExhausted: exhausted,
          })),
        replaceRevisionsFromServer: (items) =>
          set((state) => {
            const draft =
              items.find((item) => item.status === "draft") ?? null;
            const published =
              items.find((item) => item.status === "published") ?? null;
            const draftChanged =
              state.draft?.revision_id !== draft?.revision_id ||
              state.draft?.lock_version !== draft?.lock_version;
            if (state.conflicted || (state.dirty && draftChanged)) {
              return {
                revisions: items,
                revisionServerCount: items.length,
                revisionsExhausted: items.length < 20,
                draft,
                published,
                conflicted: true,
              };
            }
            return {
              revisions: items,
              revisionServerCount: items.length,
              revisionsExhausted: items.length < 20,
              draft,
              published,
              baseDefinition: draft?.definition ?? null,
              workingDefinition: draft?.definition ?? null,
              pendingOutput: draft?.definition.output ?? state.pendingOutput,
              dirty: false,
              conflicted: false,
              previewReport: draft?.validation_report ?? null,
            };
          }),
        discardLocalAndReplaceRevisions: (items) =>
          set(() => {
            const draft =
              items.find((item) => item.status === "draft") ?? null;
            return {
              revisions: items,
              revisionServerCount: items.length,
              revisionsExhausted: items.length < 20,
              draft,
              published:
                items.find((item) => item.status === "published") ?? null,
              baseDefinition: draft?.definition ?? null,
              workingDefinition: draft?.definition ?? null,
              pendingOutput: draft?.definition.output ?? { mode: "json" },
              dirty: false,
              conflicted: false,
              previewReport: draft?.validation_report ?? null,
              aiCandidate: null,
              aiPreview: null,
              aiReceipt: null,
            };
          }),
        replaceRevision: (revision) =>
          set((state) => {
            const wasDraft =
              state.draft?.revision_id === revision.revision_id;
            const nextDraft =
              revision.status === "draft"
                ? revision
                : wasDraft
                  ? null
                  : state.draft;
            return {
              revisions: prependById(
                state.revisions,
                revision,
                "revision_id",
              ),
              draft: nextDraft,
              published:
                revision.status === "published"
                  ? revision
                  : state.published?.revision_id === revision.revision_id
                    ? null
                    : state.published,
              baseDefinition:
                revision.status === "draft"
                  ? revision.definition
                  : wasDraft
                    ? null
                    : state.baseDefinition,
              workingDefinition:
                revision.status === "draft"
                  ? revision.definition
                  : wasDraft
                    ? null
                    : state.workingDefinition,
              dirty:
                wasDraft || revision.status === "draft" ? false : state.dirty,
            };
          }),
        removeRevision: (revisionId) =>
          set((state) => {
            const removedDraft = state.draft?.revision_id === revisionId;
            return {
              revisions: state.revisions.filter(
                (item) => item.revision_id !== revisionId,
              ),
              draft: removedDraft ? null : state.draft,
              published:
                state.published?.revision_id === revisionId
                  ? null
                  : state.published,
              baseDefinition: removedDraft ? null : state.baseDefinition,
              workingDefinition: removedDraft ? null : state.workingDefinition,
              dirty: removedDraft ? false : state.dirty,
              previewReport: removedDraft ? null : state.previewReport,
              conflicted: removedDraft ? false : state.conflicted,
              aiCandidate: removedDraft ? null : state.aiCandidate,
              aiPreview: removedDraft ? null : state.aiPreview,
              aiReceipt: removedDraft ? null : state.aiReceipt,
            };
          }),
        setActivePointerTarget: (activePointerTarget) =>
          set({ activePointerTarget }),
        setDefinitionView: (definitionView) => set({ definitionView }),
        setExpandedFieldIndex: (expandedFieldIndex) =>
          set({ expandedFieldIndex }),
        setActiveSection: (activeSection) => set({ activeSection }),
      }),
    ),
  );
}

export type ParserWorkspaceStore = ReturnType<
  typeof createParserWorkspaceStore
>;
export type ParserWorkspaceSnapshot = ParserWorkspaceState &
  ParserWorkspaceActions;
