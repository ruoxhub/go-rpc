"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Feedback } from "../../../_components/Feedback";
import { FormField } from "../../../_components/FormField";
import { SubmitButton } from "../../../_components/SubmitButton";
import { Button } from "../../../../_components/ui/button";
import { Card } from "../../../../_components/ui/card";
import { Select } from "../../../../_components/ui/select";
import {
  CrawlerApiError,
  crawlerRequest,
} from "../../../../../utils/crawler/crawler-api";
import type {
  Action,
  Platform,
  Task,
  TaskAnalysisConfig,
} from "../../../../../utils/crawler/crawler-types";
import { TASK_PRIORITIES } from "../../../../../utils/crawler/crawler-types";
import { taskPriorityLabel } from "../../_utils/taskPriority";
import { t } from "../../../../i18n";

import { ScheduleSettings } from "../ScheduleSettings";
import { SourceConfigFields } from "../SourceConfigFields";
import { SinkConfigFields } from "./components/SinkConfigFields";
import { DownloadConfigFields } from "./components/DownloadConfigFields";
import { useScheduleForm } from "./hooks/useScheduleForm";
import { useTaskMetadata } from "./hooks/useTaskMetadata";
import {
  initialMapping,
  taskPayload,
} from "./utils/taskForm";

interface TaskFormProps {
  mode: "create" | "edit";
  platforms: Platform[];
  actions: Action[];
  task?: Task;
}

type ReviewRouteValue = NonNullable<TaskAnalysisConfig["review_route"]> | "";

function initialSelection(
  mode: TaskFormProps["mode"],
  platforms: Platform[],
  actions: Action[],
  task?: Task,
) {
  const historicalPlatform = platforms.find(
    (platform) => platform.bs_id === task?.platform_id,
  );
  const platformId =
    historicalPlatform?.bs_id ??
    platforms.find((platform) => platform.bs_status !== "D")?.bs_id ??
    0;
  const historicalAction = actions.find(
    (action) => action.ba_id === task?.ba_id,
  );
  const validHistoricalAction =
    mode === "edit" &&
    historicalAction?.bs_id === platformId &&
    historicalAction.ba_enabled
      ? historicalAction
      : undefined;
  const defaultAction =
    mode === "create"
      ? actions.find(
          (action) => action.bs_id === platformId && action.ba_enabled,
        )
      : undefined;
  return {
    platformId,
    actionId: validHistoricalAction?.ba_id ?? defaultAction?.ba_id ?? 0,
    historicalUnavailable:
      mode === "edit" && !validHistoricalAction ? task?.action : undefined,
  };
}

export function TaskForm({ mode, platforms, actions, task }: TaskFormProps) {
  const router = useRouter();
  const selection = initialSelection(mode, platforms, actions, task);
  const initialColumns = task?.config?.source
    ? Array.from(
        new Set([
          task.config.source.key_column,
          ...task.config.source.extra_columns,
        ]),
      )
    : [];
  const [platformId, setPlatformId] = useState(selection.platformId);
  const [actionId, setActionId] = useState(selection.actionId);
  const [historicalUnavailable, setHistoricalUnavailable] = useState(
    selection.historicalUnavailable,
  );
  const [table, setTable] = useState(task?.config?.source?.table ?? "");
  const [keyColumn, setKeyColumn] = useState(
    task?.config?.source?.key_column ?? "",
  );
  const [parameterMapping, setParameterMapping] = useState(
    initialMapping(task),
  );
  const [feedback, setFeedback] = useState<string>();
  const [loading, setLoading] = useState(false);
  const { value: scheduleValue, setValue: setScheduleValue } = useScheduleForm(task);
  const [executor, setExecutor] = useState(task?.config?.executor ?? "rpc_crawl");
  const initialModelId = task?.config?.analysis?.llm_model_id ?? null;
  const [llmModelId, setLlmModelId] = useState(
    initialModelId?.toString() ?? "",
  );
  const [reviewRoute, setReviewRoute] = useState<ReviewRouteValue>(
    task?.config?.analysis?.review_route ?? "",
  );
  const metadata = useTaskMetadata(
    selection.actionId,
    initialColumns,
    executor === "video_analysis",
  );
  const historicalModelUnavailable =
    executor === "video_analysis" &&
    metadata.llmModelsLoaded &&
    initialModelId !== null &&
    llmModelId === initialModelId.toString() &&
    !metadata.llmModels.some((model) => model.id === initialModelId);
  const availableActions = actions.filter(
    (action) => action.bs_id === platformId && action.ba_enabled,
  );

  function changePlatform(value: number) {
    setPlatformId(value);
    setActionId(0);
    setHistoricalUnavailable(undefined);
    metadata.clearSchema();
  }

  function changeAction(value: number) {
    metadata.clearSchema();
    setHistoricalUnavailable(undefined);
    setActionId(value);
    if (value) void metadata.loadSchema(value);
  }

  function changeTable(value: string) {
    setTable(value);
    setKeyColumn("");
    setParameterMapping("");
    metadata.clearColumns();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedback(undefined);
    if (!actionId) {
      setFeedback(t("tasks.chooseAction"));
      return;
    }
    const payload = taskPayload({
      data: new FormData(event.currentTarget),
      actionId,
      table,
      keyColumn,
      parameterMapping,
      schedule: scheduleValue,
      executor,
    });
    setLoading(true);
    try {
      await crawlerRequest<Task>(
        mode === "edit" ? `/tasks/${task?.task_id}` : "/tasks",
        {
          method: mode === "edit" ? "PUT" : "POST",
          body: JSON.stringify(payload),
        },
      );
      router.push("/crawler/tasks");
    } catch (error) {
      setFeedback(
        error instanceof CrawlerApiError
          ? error.message
          : t("tasks.saveUnknownError"),
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="p-6 shadow-sm">
      <form onSubmit={submit} className="grid gap-5">
        {feedback ? <Feedback variant="error">{feedback}</Feedback> : null}
        <div className="grid gap-4 md:grid-cols-2">
          <FormField id="priority" label={t("tasks.priority")} required>
            <Select
              id="priority"
              name="priority"
              aria-label={t("tasks.priority")}
              defaultValue={task?.priority ?? "normal"}
              className="bg-background"
            >
              {TASK_PRIORITIES.map((priority) => (
                <option key={priority} value={priority}>
                  {taskPriorityLabel(priority)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="executor" label={t("tasks.executor")} required>
            <Select
              name="executor"
              aria-label={t("tasks.executor")}
              value={executor}
              onChange={(event) => setExecutor(event.target.value as typeof executor)}
              className="bg-background"
            >
              <option value="rpc_crawl">{t("tasks.executorRpcCrawl")}</option>
              <option value="video_clean">{t("tasks.executorVideoClean")}</option>
              <option value="video_download">{t("tasks.executorVideoDownload")}</option>
              <option value="video_analysis">{t("tasks.executorVideoAnalysis")}</option>
            </Select>
          </FormField>
          <FormField id="platform_id" label={t("nav.platforms")} required>
            <Select
              aria-label={t("nav.platforms")}
              value={platformId}
              onChange={(event) => changePlatform(Number(event.target.value))}
              className="bg-background"
            >
              {platforms.map((platform) => (
                <option key={platform.bs_id} value={platform.bs_id}>
                  {platform.bs_name ??
                    platform.bs_platform_code ??
                    t("tasks.platformName", { id: platform.bs_id })}
                  {platform.bs_status === "D" ? t("actions.deletedSuffix") : ""}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="ba_id" label={t("nav.actions")} required>
            <Select
              aria-label={t("nav.actions")}
              value={actionId}
              onChange={(event) => changeAction(Number(event.target.value))}
              className="bg-background"
            >
              <option value="">{t("tasks.choose")}</option>
              {availableActions.map((action) => (
                <option key={action.ba_id} value={action.ba_id}>
                  {action.ba_action}
                </option>
              ))}
            </Select>
          </FormField>
        </div>
        {historicalUnavailable ? (
          <Feedback variant="warning">
            {historicalUnavailable}{t("tasks.unavailableSuffix")}
          </Feedback>
        ) : null}
        {metadata.schemaError ? (
          <Feedback variant="error">
            <span>{metadata.schemaError}</span>{" "}
            <Button
              type="button"
              variant="link"
              size="sm"
              className="h-auto p-0 font-medium underline"
              onClick={() => metadata.loadSchema(actionId)}
            >
              {t("tasks.retrySchema")}
            </Button>
          </Feedback>
        ) : null}
        {metadata.schema !== undefined ? (
          <details className="rounded-md bg-muted p-3 text-xs">
            <summary className="cursor-pointer font-medium">{t("tasks.actionSchema")}</summary>
            <pre className="mt-2 overflow-auto">
              {JSON.stringify(metadata.schema, null, 2)}
            </pre>
          </details>
        ) : null}
        <SourceConfigFields
          table={table}
          columns={metadata.columns}
          keyColumn={keyColumn}
          parameterMapping={parameterMapping}
          loading={metadata.columnLoading}
          error={metadata.columnError}
          initialWhere={task?.config?.source?.where ?? ""}
          onTableChange={changeTable}
          onKeyColumnChange={setKeyColumn}
          onParameterMappingChange={setParameterMapping}
          onLoadColumns={() => metadata.loadColumns(table)}
        />
        <SinkConfigFields task={task} />
        {executor === "video_download" ? <DownloadConfigFields task={task} /> : null}
        {executor === "video_analysis" ? (
          <div className="grid gap-2">
            <div className="grid gap-4 md:grid-cols-2">
              <FormField
                id="llm_model_id"
                label={t("tasks.analysisModel")}
                error={historicalModelUnavailable ? t("tasks.selectedModelUnavailable") : undefined}
              >
                <Select
                  name="llm_model_id"
                  value={llmModelId}
                  onChange={(event) => setLlmModelId(event.target.value)}
                  disabled={metadata.llmModelsLoading}
                  className="bg-background"
                >
                  <option value="">{t("tasks.useDefaultModel")}</option>
                  {historicalModelUnavailable ? (
                    <option value={initialModelId ?? undefined} disabled>
                      {t("tasks.unavailableModel", { id: initialModelId ?? "" })}
                    </option>
                  ) : null}
                  {metadata.llmModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.display_name}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id="review_route" label={t("tasks.reviewRoute")}>
                <Select
                  name="review_route"
                  value={reviewRoute}
                  onChange={(event) => {
                    const value = event.target.value;
                    if (value === "" || value === "R" || value === "G") {
                      setReviewRoute(value);
                    }
                  }}
                  className="bg-background"
                >
                  <option value="">{t("tasks.reviewRouteUnknown")}</option>
                  <option value="R">{t("tasks.reviewRouteReference")}</option>
                  <option value="G">{t("tasks.reviewRouteGenerated")}</option>
                </Select>
              </FormField>
            </div>
            {metadata.llmModelsError ? (
              <Feedback variant="error">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span>{metadata.llmModelsError}</span>
                  <SubmitButton
                    type="button"
                    loading={metadata.llmModelsLoading}
                    loaderClassName="motion-reduce:animate-none"
                    className="touch-target"
                    onClick={metadata.reloadLlmModels}
                  >
                    {t("tasks.retryModels")}
                  </SubmitButton>
                </div>
              </Feedback>
            ) : null}
          </div>
        ) : null}
        <ScheduleSettings
          value={scheduleValue}
          timezone="Asia/Shanghai"
          onChange={setScheduleValue}
        />
        <div className="flex justify-end gap-2">
          <Button asChild variant="outline">
            <Link href="/crawler/tasks">
              {t("common.cancel")}
            </Link>
          </Button>
          <SubmitButton
            loading={loading}
            disabled={metadata.llmModelsLoading || Boolean(metadata.llmModelsError) || historicalModelUnavailable}
          >
            {mode === "create" ? t("tasks.create") : t("common.save")}
          </SubmitButton>
        </div>
      </form>
    </Card>
  );
}
