// ParserPage：服务端并行装配解析器工作台首屏数据。
import { notFound } from "next/navigation";

import {
  getParserCapabilities,
  listParserRevisions,
  listParserSamples,
} from "../../../../../api/action-parser/action-parser.api";
import {
  getActionParamSchema,
  getParserLlmModels,
} from "../../../../../api/task-metadata/task-metadata.api";
import { t } from "../../../../i18n";
import {
  CrawlerApiError,
  crawlerRequest,
} from "../../../../../utils/crawler/crawler-api";
import type {
  Action,
  PlatformList,
} from "@/utils/crawler/crawler-types";

import { ParserWorkspace } from "./_components/ParserWorkspace";
import { createInitialWorkspaceState } from "./_components/ParserWorkspace/types";

export const dynamic = "force-dynamic";

export default async function ParserPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const rawId = (await params).id;
  if (!/^[1-9]\d*$/.test(rawId)) notFound();
  const baId = Number(rawId);
  if (!Number.isSafeInteger(baId)) notFound();

  const [
    actionResult,
    platformsResult,
    actionSchemaResult,
    capabilitiesResult,
    samplesResult,
    revisionsResult,
    modelsResult,
  ] = await Promise.allSettled([
    crawlerRequest<Action>(`/actions/${baId}`),
    crawlerRequest<PlatformList>("/platforms?include_deleted=false"),
    getActionParamSchema(baId),
    getParserCapabilities(),
    listParserSamples(baId, { offset: 0, limit: 20 }),
    listParserRevisions(baId, { offset: 0, limit: 20 }),
    getParserLlmModels(),
  ]);
  if (actionResult.status === "rejected") {
    if (
      actionResult.reason instanceof CrawlerApiError &&
      actionResult.reason.status === 404
    ) {
      notFound();
    }
    throw actionResult.reason;
  }

  function unwrap<T>(result: PromiseSettledResult<T>) {
    if (result.status === "rejected") throw result.reason;
    return result.value;
  }

  const action = actionResult.value;
  const platforms = unwrap(platformsResult);
  const actionSchema = unwrap(actionSchemaResult);
  const capabilities = unwrap(capabilitiesResult);
  const samples = unwrap(samplesResult);
  const revisions = unwrap(revisionsResult);
  const models = unwrap(modelsResult);
  const platform = platforms.items.find((item) => item.bs_id === action.bs_id);
  const platformName =
    platform?.bs_name ??
    platform?.bs_platform_code ??
    t("actions.platformName", { id: action.bs_id });

  return (
    <ParserWorkspace
      initialState={createInitialWorkspaceState({
        action,
        platformName,
        actionSchema: actionSchema.schema,
        capabilities,
        llmModels: models.llm_models,
        samples: samples.items,
        sampleServerCount: samples.items.length,
        samplesExhausted: samples.items.length < 20,
        revisions: revisions.items,
        revisionServerCount: revisions.items.length,
        revisionsExhausted: revisions.items.length < 20,
        draft:
          revisions.items.find((item) => item.status === "draft") ?? null,
        published:
          revisions.items.find((item) => item.status === "published") ?? null,
      })}
    />
  );
}
