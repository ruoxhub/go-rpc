export type ParserFieldType = "string" | "integer" | "number" | "boolean" | "datetime" | "object" | "array";
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export interface ParserOutput { mode: "json" | "model"; datatype?: string | null }
export interface ParserFieldMapping { target: string; source?: string; value?: JsonValue; type?: ParserFieldType | null; default?: JsonValue; required?: boolean }
export interface ParserDefinition { schema_version: 1; record_path: string; output: ParserOutput; fields: ParserFieldMapping[] }
export type ParserRevisionStatus = "draft" | "published" | "archived";
export type ParserRevisionSource = "manual" | "ai" | "restore";
export interface ParserModelField { target: string; required: boolean; value_types: ParserFieldType[] }
export interface ParserCapabilities { model_datatypes: string[]; field_types: ParserFieldType[]; model_fields: Record<string, ParserModelField[]> }
export interface ParserSample { sample_id: number; ba_id: number; response_sha256: string; response_bytes: number; sanitizer_version: string; rpc_duration_ms: number; created_at: string }
export interface ParserSampleDetail extends ParserSample { redacted_preview: JsonValue }
export interface ParserSampleList { items: ParserSample[] }
export interface ParserPreviewError { sample_id: number; record_index?: number; target?: string | null; code: string }
export interface ParserPreviewReport { definition_sha256: string; samples: Array<{ sample_id: number; sample_sha256: string }>; sample_ids: number[]; source_records: number; valid_records: number; invalid_records: number; passed: boolean; errors: ParserPreviewError[]; errors_truncated: boolean; preview: JsonValue[] }
export interface ParserRevision { revision_id: number; ba_id: number; revision_no: number; status: ParserRevisionStatus; definition: ParserDefinition; definition_sha256: string; source: ParserRevisionSource; source_sample_id: number | null; restored_from_revision_id: number | null; validation_report: ParserPreviewReport | null; lock_version: number; generation_metadata: Record<string, JsonValue> | null; created_at: string; updated_at: string; published_at: string | null }
export interface ParserRevisionList { items: ParserRevision[] }
export interface ParserAssistResult { definition: ParserDefinition; preview: JsonValue[]; assistReceipt: string }
export interface ParserPage { offset: number; limit: number }
export interface ParserSampleCreatePayload { params: Record<string, JsonValue>; confirm_side_effect: boolean }
export interface ParserSuggestionPayload { sample_id: number; model_id: number; output: ParserOutput }
export interface ParserAssistPayload extends ParserSuggestionPayload { lock_version: number }
export interface ParserRevisionSavePayload { definition: ParserDefinition; assistReceipt?: string }
export interface ParserPreviewPayload { lock_version: number; sample_ids: number[] }
