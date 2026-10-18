import { crawlerRequest } from "../../utils/crawler/crawler-api";
import type {
  JsonValue, ParserAssistPayload, ParserAssistResult, ParserCapabilities, ParserDefinition,
  ParserPage, ParserPreviewPayload, ParserPreviewReport, ParserRevision, ParserRevisionList,
  ParserRevisionSavePayload, ParserSample, ParserSampleCreatePayload, ParserSampleDetail,
  ParserSampleList, ParserSuggestionPayload,
} from "./action-parser.types";

interface ParserAssistWire { definition: ParserDefinition; preview: JsonValue[]; assist_receipt: string }
function parserAssistResult(wire: ParserAssistWire): ParserAssistResult {
  return { definition: wire.definition, preview: wire.preview, assistReceipt: wire.assist_receipt };
}
function pageQuery(page: ParserPage) {
  return new URLSearchParams({ offset: String(page.offset), limit: String(page.limit) });
}

export const getParserCapabilities = () => crawlerRequest<ParserCapabilities>("/parser-capabilities");
export const listParserSamples = (baId: number, page: ParserPage) => crawlerRequest<ParserSampleList>(`/actions/${baId}/parser-samples?${pageQuery(page)}`);
export const getParserSample = (baId: number, sampleId: number) => crawlerRequest<ParserSampleDetail>(`/actions/${baId}/parser-samples/${sampleId}`);
export const createParserSample = (baId: number, payload: ParserSampleCreatePayload) => crawlerRequest<ParserSample>(`/actions/${baId}/parser-samples`, { method: "POST", body: JSON.stringify(payload) });
export const deleteParserSample = (baId: number, sampleId: number) => crawlerRequest<void>(`/actions/${baId}/parser-samples/${sampleId}`, { method: "DELETE" });
export const listParserRevisions = (baId: number, page: ParserPage) => crawlerRequest<ParserRevisionList>(`/actions/${baId}/parser-revisions?${pageQuery(page)}`);
export const getParserRevision = (baId: number, revisionId: number) => crawlerRequest<ParserRevision>(`/actions/${baId}/parser-revisions/${revisionId}`);
export function saveParserRevision(baId: number, draft: Pick<ParserRevision, "revision_id" | "lock_version"> | undefined, payload: ParserRevisionSavePayload) {
  const body = { definition: payload.definition, ...(payload.assistReceipt ? { assist_receipt: payload.assistReceipt } : {}), ...(draft ? { lock_version: draft.lock_version } : {}) };
  return crawlerRequest<ParserRevision>(draft ? `/actions/${baId}/parser-revisions/${draft.revision_id}` : `/actions/${baId}/parser-revisions`, { method: draft ? "PATCH" : "POST", body: JSON.stringify(body) });
}
export const deleteParserDraft = (baId: number, revisionId: number) => crawlerRequest<void>(`/actions/${baId}/parser-revisions/${revisionId}`, { method: "DELETE" });
export async function suggestParserDefinition(baId: number, payload: ParserSuggestionPayload) { return parserAssistResult(await crawlerRequest<ParserAssistWire>(`/actions/${baId}/parser-suggestions`, { method: "POST", body: JSON.stringify(payload) })); }
export async function assistParserDefinition(baId: number, revisionId: number, payload: ParserAssistPayload) { return parserAssistResult(await crawlerRequest<ParserAssistWire>(`/actions/${baId}/parser-revisions/${revisionId}/assist`, { method: "POST", body: JSON.stringify(payload) })); }
export const previewParserRevision = (baId: number, revisionId: number, payload: ParserPreviewPayload) => crawlerRequest<ParserPreviewReport>(`/actions/${baId}/parser-revisions/${revisionId}/preview`, { method: "POST", body: JSON.stringify(payload) });
export const publishParserRevision = (baId: number, revisionId: number) => crawlerRequest<ParserRevision>(`/actions/${baId}/parser-revisions/${revisionId}/publish`, { method: "POST" });
export const archiveParserRevision = (baId: number, revisionId: number) => crawlerRequest<ParserRevision>(`/actions/${baId}/parser-revisions/${revisionId}/archive`, { method: "POST" });
export const restoreParserRevision = (baId: number, revisionId: number) => crawlerRequest<ParserRevision>(`/actions/${baId}/parser-revisions/${revisionId}/restore`, { method: "POST" });
