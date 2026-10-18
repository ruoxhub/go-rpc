import { crawlerRequest } from "../../utils/crawler/crawler-api";
import type { ActionSchemaResponse, LlmModelMetadataResponse } from "./task-metadata.types";

export const getActionParamSchema = (baId: number) =>
  crawlerRequest<ActionSchemaResponse>(`/tasks/meta/action-schemas/${baId}`);

export const getParserLlmModels = () =>
  crawlerRequest<LlmModelMetadataResponse>("/tasks/meta/llm-models");
