// ModelList：展示提供商模型及其远端可用、启停状态，支持搜索过滤和定高滚动。
"use client";

import { useMemo, useState } from "react";
import { Loader2 } from "../../../../../_components/Loader2";
import { Button } from "../../../../../_components/ui/button";
import { Input } from "../../../../../_components/ui/input";
import { t } from "../../../../../i18n";
import type { LlmModel } from "../../../../utils/settings-types";

export function ModelList({
  models,
  loading,
  disabled,
  pendingModelIds,
  onToggle,
}: {
  models: LlmModel[];
  loading: boolean;
  disabled: boolean;
  pendingModelIds: ReadonlySet<number>;
  onToggle: (model: LlmModel) => void;
}) {
  const [search, setSearch] = useState("");

  const filteredModels = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return models;
    return models.filter(
      (model) =>
        model.display_name.toLowerCase().includes(query) ||
        model.remote_model_id.toLowerCase().includes(query) ||
        model.litellm_model.toLowerCase().includes(query)
    );
  }, [models, search]);

  const enabledCount = useMemo(
    () => models.filter((model) => model.enabled).length,
    [models]
  );

  if (loading) {
    return (
      <div aria-label={t("settings.providers.modelsLoading")} className="space-y-2">
        <div className="h-12 animate-pulse rounded-md bg-muted motion-reduce:animate-none" />
        <div className="h-12 animate-pulse rounded-md bg-muted motion-reduce:animate-none" />
      </div>
    );
  }

  if (models.length === 0) {
    return (
      <p className="rounded-md bg-muted px-3 py-4 text-sm text-muted-foreground">
        {t("settings.providers.modelsEmpty")}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-muted-foreground">
          {t("settings.providers.modelStats", {
            total: models.length,
            enabled: enabledCount,
          })}
        </p>
        <div className="w-full sm:max-w-xs">
          <Input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("settings.providers.searchPlaceholder")}
            aria-label={t("settings.providers.searchPlaceholder")}
            className="touch-target"
          />
        </div>
      </div>

      <div className="max-h-96 overflow-y-auto rounded-lg border border-border">
        {filteredModels.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-muted-foreground">
            {t("settings.providers.noMatch")}
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {filteredModels.map((model) => {
              const busy = pendingModelIds.has(model.id);
              return (
                <li
                  key={model.id}
                  className="flex flex-col gap-3 p-3 transition-colors hover:bg-muted/30 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">
                      {model.display_name}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {model.litellm_model}
                    </p>
                    {!model.remote_available ? (
                      <p className="mt-1 text-xs text-warning-strong">
                        {t("settings.providers.modelUnavailable")}
                      </p>
                    ) : null}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={
                      disabled ||
                      busy ||
                      (!model.remote_available && !model.enabled)
                    }
                    aria-busy={busy}
                    onClick={() => onToggle(model)}
                    className="touch-target shrink-0 px-3"
                  >
                    {busy ? (
                      <Loader2 className="mr-2 motion-reduce:animate-none" />
                    ) : null}
                    {model.enabled
                      ? t("settings.providers.disableModel")
                      : t("settings.providers.enableModel")}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
