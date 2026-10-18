import { useCallback, useEffect, useRef, useState } from "react";

import {
  CrawlerApiError,
  crawlerRequest,
} from "../../../../../../utils/crawler/crawler-api";
import {
  getActionParamSchema,
  getParserLlmModels,
} from "../../../../../../api/task-metadata/task-metadata.api";
import type {
  TableColumnsResponse,
} from "../../../../../../utils/crawler/crawler-types";
import type {
  ActionSchemaResponse,
  LlmModelMetadataResponse,
} from "../../../../../../api/task-metadata/task-metadata.types";
import { t } from "../../../../../i18n";

function errorMessage(error: unknown, fallback: string) {
  return error instanceof CrawlerApiError ? error.message : fallback;
}

export function useTaskMetadata(
  initialActionId: number,
  initialColumns: string[],
  loadLlmModels: boolean,
) {
  const [schema, setSchema] = useState<ActionSchemaResponse["schema"]>();
  const [schemaError, setSchemaError] = useState<string>();
  const [columns, setColumns] = useState<string[]>(initialColumns);
  const [columnError, setColumnError] = useState<string>();
  const [columnLoading, setColumnLoading] = useState(false);
  const [llmModels, setLlmModels] = useState<LlmModelMetadataResponse["llm_models"]>([]);
  const [llmModelsLoading, setLlmModelsLoading] = useState(loadLlmModels);
  const [llmModelsError, setLlmModelsError] = useState<string>();
  const [llmModelsLoaded, setLlmModelsLoaded] = useState(false);
  const schemaRequestId = useRef(0);
  const columnRequestId = useRef(0);
  const llmModelsRequestId = useRef(0);

  const loadSchema = useCallback(async (actionId: number) => {
    const requestId = ++schemaRequestId.current;
    try {
      const response = await getActionParamSchema(actionId);
      if (requestId === schemaRequestId.current) {
        setSchema(response.schema);
        setSchemaError(undefined);
      }
    } catch (error) {
      if (requestId === schemaRequestId.current) {
        setSchema(undefined);
        setSchemaError(errorMessage(error, t("tasks.readSchemaFailed")));
      }
    }
  }, []);

  useEffect(() => {
    if (!initialActionId) return;
    const requestId = ++schemaRequestId.current;
    getActionParamSchema(initialActionId)
      .then((response) => {
        if (requestId === schemaRequestId.current) setSchema(response.schema);
      })
      .catch((error) => {
        if (requestId === schemaRequestId.current) {
          setSchemaError(errorMessage(error, t("tasks.readSchemaFailed")));
        }
      });
  }, [initialActionId]);

  const reloadLlmModels = useCallback(async () => {
    const requestId = ++llmModelsRequestId.current;
    setLlmModelsLoading(true);
    try {
      const response = await getParserLlmModels();
      if (requestId === llmModelsRequestId.current) {
        setLlmModels(response.llm_models);
        setLlmModelsError(undefined);
        setLlmModelsLoaded(true);
      }
    } catch (error) {
      if (requestId === llmModelsRequestId.current) {
        setLlmModelsError(errorMessage(error, t("tasks.readModelsFailed")));
        setLlmModelsLoaded(false);
      }
    } finally {
      if (requestId === llmModelsRequestId.current) setLlmModelsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!loadLlmModels) return;
    const requestId = ++llmModelsRequestId.current;
    getParserLlmModels()
      .then((response) => {
        if (requestId === llmModelsRequestId.current) {
          setLlmModels(response.llm_models);
          setLlmModelsError(undefined);
          setLlmModelsLoaded(true);
        }
      })
      .catch((error) => {
        if (requestId === llmModelsRequestId.current) {
          setLlmModelsError(errorMessage(error, t("tasks.readModelsFailed")));
          setLlmModelsLoaded(false);
        }
      })
      .finally(() => {
        if (requestId === llmModelsRequestId.current) setLlmModelsLoading(false);
      });
  }, [loadLlmModels]);

  function clearSchema() {
    schemaRequestId.current += 1;
    setSchema(undefined);
    setSchemaError(undefined);
  }

  function clearColumns() {
    columnRequestId.current += 1;
    setColumns([]);
    setColumnError(undefined);
    setColumnLoading(false);
  }

  async function loadColumns(table: string) {
    const requestId = ++columnRequestId.current;
    setColumnLoading(true);
    setColumnError(undefined);
    try {
      const response = await crawlerRequest<TableColumnsResponse>(
        `/tasks/meta/table-columns?table_name=${encodeURIComponent(table.trim())}`,
      );
      if (requestId === columnRequestId.current) setColumns(response.columns);
    } catch (error) {
      if (requestId === columnRequestId.current) {
        setColumnError(errorMessage(error, t("tasks.readColumnsFailed")));
      }
    } finally {
      if (requestId === columnRequestId.current) setColumnLoading(false);
    }
  }

  return {
    schema,
    schemaError,
    columns,
    columnError,
    columnLoading,
    clearSchema,
    clearColumns,
    loadSchema,
    loadColumns,
    setColumns,
    llmModels,
    llmModelsLoading,
    llmModelsError,
    llmModelsLoaded,
    reloadLlmModels,
  };
}
