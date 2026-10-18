"use client";

import { useCallback, useRef, useState, type KeyboardEvent } from "react";
import { Alert, AlertDescription } from "../../../_components/ui/alert";
import { t } from "../../../i18n";
import type { LlmModel, LlmProvider, SettingsResponse } from "../../utils/settings-types";
import { AnalysisVideoForm } from "../forms/AnalysisVideoForm";
import { CleanerForm } from "../forms/CleanerForm";
import { PlatformPolicyEditor } from "../PlatformPolicyEditor";
import { LlmForm } from "../forms/LlmForm";
import { ProxyForm } from "../forms/ProxyForm";
import { RpcForm } from "../forms/RpcForm";
import { SchedulerForm } from "../forms/SchedulerForm";
import { ProviderManager } from "../ProviderManager";

const tabs = ["ai", "media", "scheduler", "network", "cleaner"] as const;
type Tab = typeof tabs[number];
const labels: Record<Tab, Parameters<typeof t>[0]> = {
  ai: "settings.tabs.ai",
  media: "settings.tabs.media",
  scheduler: "settings.tabs.scheduler",
  network: "settings.tabs.network",
  cleaner: "settings.tabs.cleaner",
};

export function SettingsClient({ initialSettings, initialProviders = [], initialModels = [], initialModelCatalog = initialModels, modelCatalogIncomplete = false }: { initialSettings: SettingsResponse; initialProviders?: LlmProvider[]; initialModels?: LlmModel[]; initialModelCatalog?: LlmModel[]; modelCatalogIncomplete?: boolean }) {
  const [active, setActive] = useState<Tab>("ai");
  const [cleanerDirty, setCleanerDirty] = useState(false);
  const [policySaving, setPolicySaving] = useState(false);
  const [pendingTab, setPendingTab] = useState<Tab | null>(null);
  const [models, setModels] = useState(initialModels);
  const [catalogModels, setCatalogModels] = useState(initialModelCatalog);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  function requestTab(tab: Tab) {
    if (policySaving) return;
    if (active === "cleaner" && tab !== "cleaner" && cleanerDirty) {
      setPendingTab(tab);
      return;
    }
    setActive(tab);
  }

  function selectTab(index: number) {
    const tab = tabs[(index + tabs.length) % tabs.length];
    if ((active === "cleaner" && cleanerDirty) || policySaving) {
      requestTab(tab);
      return;
    }
    requestTab(tab);
    tabRefs.current[tabs.indexOf(tab)]?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const destinations: Partial<Record<string, number>> = {
      ArrowRight: index + 1,
      ArrowDown: index + 1,
      ArrowLeft: index - 1,
      ArrowUp: index - 1,
      Home: 0,
      End: tabs.length - 1,
    };
    const destination = destinations[event.key];
    if (destination === undefined) return;
    event.preventDefault();
    selectTab(destination);
  }

  const replaceProviderModels = useCallback((providerId: number, providerModels: LlmModel[], providerCatalog = providerModels) => {
    setModels((items) => [
      ...items.filter((model) => model.provider_id !== providerId),
      ...providerModels.filter((model) => model.enabled && model.remote_available),
    ]);
    setCatalogModels((items) => [
      ...items.filter((model) => model.provider_id !== providerId),
      ...providerCatalog,
    ]);
  }, []);

  return (
    <div className="space-y-5">
      <div className="overflow-x-auto border-b border-border">
        <div role="tablist" aria-label={t("settings.tabs.label")} className="flex min-w-max gap-1">
          {tabs.map((tab, index) => (
            <button
              key={tab}
              ref={(element) => { tabRefs.current[index] = element; }}
              id={`settings-tab-${tab}`}
              type="button"
              role="tab"
              tabIndex={active === tab ? 0 : -1}
              aria-selected={active === tab}
              aria-controls={`settings-panel-${tab}`}
              onClick={() => requestTab(tab)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              className={`cursor-pointer border-b-2 px-4 py-3 text-sm font-medium transition-colors ${active === tab ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              {t(labels[tab])}
            </button>
          ))}
        </div>
      </div>
      <div id="settings-panel-ai" role="tabpanel" aria-labelledby="settings-tab-ai" hidden={active !== "ai"} className="space-y-5">
        {modelCatalogIncomplete ? (
          <Alert variant="default" role="status" className="px-3 py-2 text-sm text-muted-foreground">
            <AlertDescription>{t("settings.llm.catalogIncomplete")}</AlertDescription>
          </Alert>
        ) : null}
        <LlmForm value={initialSettings.llm} models={models} catalogModels={catalogModels} />
        <ProviderManager initialProviders={initialProviders} onUsableModelsChange={replaceProviderModels} />
      </div>
      <div id="settings-panel-media" role="tabpanel" aria-labelledby="settings-tab-media" hidden={active !== "media"}>
        <AnalysisVideoForm value={initialSettings.analysis_video} />
      </div>
      <div id="settings-panel-scheduler" role="tabpanel" aria-labelledby="settings-tab-scheduler" hidden={active !== "scheduler"} className="grid gap-5 xl:grid-cols-2">
        <SchedulerForm value={initialSettings.scheduler} />
        <RpcForm value={initialSettings.rpc} />
      </div>
      <div id="settings-panel-network" role="tabpanel" aria-labelledby="settings-tab-network" hidden={active !== "network"}>
        <ProxyForm value={initialSettings.proxy} />
      </div>
      <div id="settings-panel-cleaner" role="tabpanel" aria-labelledby="settings-tab-cleaner" hidden={active !== "cleaner"}>
        <div className="space-y-5">
          <CleanerForm value={initialSettings.cleaner} />
          <PlatformPolicyEditor
            platforms={initialSettings.platforms}
            pendingTabChange={pendingTab !== null}
            onDirtyChange={setCleanerDirty}
            onSavingChange={setPolicySaving}
            onCancelTabChange={() => {
              setPendingTab(null);
              queueMicrotask(() => tabRefs.current[tabs.indexOf(active)]?.focus());
            }}
            onConfirmTabChange={() => {
              if (pendingTab) {
                setActive(pendingTab);
                queueMicrotask(() => tabRefs.current[tabs.indexOf(pendingTab)]?.focus());
              }
              setPendingTab(null);
            }}
          />
        </div>
      </div>
    </div>
  );
}
