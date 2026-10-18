export interface ActionSchemaResponse {
  schema: Record<string, unknown> | unknown[] | boolean;
}

export interface LlmModelOption {
  id: number;
  display_name: string;
  litellm_model: string;
}

export interface LlmModelMetadataResponse {
  llm_models: LlmModelOption[];
}
