// ProviderManager：维护模型提供商、同步目录并控制模型可用状态。
"use client";

import { useEffect, useRef, useState } from "react";
import { ConfirmDialog } from "../../../_components/ConfirmDialog";
import { Loader2 } from "../../../_components/Loader2";
import { Button } from "../../../_components/ui/button";
import { Card } from "../../../_components/ui/card";
import { Alert, AlertDescription } from "../../../_components/ui/alert";
import { t } from "../../../i18n";
import { createProvider, deleteProvider, listProviderModels, setModelEnabled, setProviderEnabled, syncProviderModels, updateProvider } from "../../utils/settings-api";
import type { LlmModel, LlmProvider, ProviderCreate, ProviderUpdate } from "../../utils/settings-types";
import { ModelList } from "./components/ModelList";
import { ProviderForm } from "./components/ProviderForm";

export function ProviderManager({ initialProviders, onUsableModelsChange }: { initialProviders: LlmProvider[]; onUsableModelsChange?: (providerId: number, models: LlmModel[], catalogModels?: LlmModel[]) => void }) {
  const [providers, setProviders] = useState(initialProviders);
  const enabledProviderIdsRef = useRef(new Set(initialProviders.filter((provider) => provider.enabled).map((provider) => provider.id)));
  const [selectedId, setSelectedId] = useState<number | null>(initialProviders[0]?.id ?? null);
  const selectedIdRef = useRef(selectedId);
  const [creating, setCreating] = useState(initialProviders.length === 0);
  const [models, setModels] = useState<LlmModel[]>([]);
  const modelsRef = useRef<LlmModel[]>([]);
  const modelsByProviderRef = useRef(new Map<number, LlmModel[]>());
  const [loadedProviderId, setLoadedProviderId] = useState<number | null>(null);
  const [syncingId, setSyncingId] = useState<number | null>(null);
  const [pendingModelIds, setPendingModelIds] = useState<Set<number>>(() => new Set());
  const [providerBusy, setProviderBusy] = useState(false);
  const [providerSaving, setProviderSaving] = useState(false);
  const [deletingProvider, setDeletingProvider] = useState<LlmProvider | null>(null);
  const [deleteError, setDeleteError] = useState(false);
  const [feedback, setFeedback] = useState<{ error: boolean; message: string } | null>(null);
  const selected = providers.find((item) => item.id === selectedId) ?? null;
  const modelsLoading = selectedId !== null && loadedProviderId !== selectedId;

  function selectProviderId(providerId: number | null) {
    if (selectedIdRef.current !== providerId) modelsRef.current = [];
    selectedIdRef.current = providerId;
    setSelectedId(providerId);
  }

  useEffect(() => {
    if (!selectedId) return;
    let current = true;
    listProviderModels(selectedId, "all")
      .then((items) => { if (current && selectedIdRef.current === selectedId) { modelsByProviderRef.current.set(selectedId, items); modelsRef.current = items; setModels(items); setLoadedProviderId(selectedId); onUsableModelsChange?.(selectedId, enabledProviderIdsRef.current.has(selectedId) ? items : [], items); } })
      .catch(() => { if (current && selectedIdRef.current === selectedId) { modelsRef.current = []; setModels([]); setLoadedProviderId(selectedId); setFeedback({ error: true, message: t("settings.providers.modelsLoadFailed") }); } })
    return () => { current = false; };
  }, [onUsableModelsChange, selectedId]);

  function replaceProvider(provider: LlmProvider) {
    if (provider.enabled) enabledProviderIdsRef.current.add(provider.id);
    else enabledProviderIdsRef.current.delete(provider.id);
    setProviders((items) => items.map((item) => item.id === provider.id ? provider : item));
  }

  async function saveProvider(value: ProviderCreate | ProviderUpdate) {
    const saved = selected && !creating ? await updateProvider(selected.id, value as ProviderUpdate) : await createProvider(value as ProviderCreate);
    if (saved.enabled) enabledProviderIdsRef.current.add(saved.id);
    else enabledProviderIdsRef.current.delete(saved.id);
    setProviders((items) => selected && !creating ? items.map((item) => item.id === saved.id ? saved : item) : [...items, saved]);
    selectProviderId(saved.id);
    setCreating(false);
    setFeedback({ error: false, message: t("settings.providers.saveSuccess") });
  }

  async function syncModels() {
    if (!selected) return;
    setSyncingId(selected.id);
    setFeedback(null);
    try {
      await syncProviderModels(selected.id);
      if (selectedIdRef.current !== selected.id) return;
      const refreshedModels = await listProviderModels(selected.id, "all");
      if (selectedIdRef.current !== selected.id) return;
      modelsRef.current = refreshedModels;
      modelsByProviderRef.current.set(selected.id, refreshedModels);
      setModels(refreshedModels);
      setLoadedProviderId(selected.id);
      onUsableModelsChange?.(selected.id, enabledProviderIdsRef.current.has(selected.id) ? refreshedModels : [], refreshedModels);
      setFeedback({ error: false, message: t("settings.providers.syncSuccess") });
    } catch {
      if (selectedIdRef.current === selected.id) setFeedback({ error: true, message: t("settings.providers.syncFailed") });
    } finally { setSyncingId(null); }
  }

  async function toggleProvider() {
    if (!selected) return;
    const providerId = selected.id;
    const providerModels = modelsByProviderRef.current.get(providerId) ?? modelsRef.current;
    setProviderBusy(true);
    setFeedback(null);
    try {
      const updated = await setProviderEnabled(providerId, !selected.enabled);
      replaceProvider(updated);
      onUsableModelsChange?.(providerId, updated.enabled ? providerModels : [], providerModels);
    }
    catch { setFeedback({ error: true, message: t("settings.providers.operationFailed") }); }
    finally { setProviderBusy(false); }
  }

  async function toggleModel(model: LlmModel) {
    const providerId = model.provider_id;
    const providerModels = modelsByProviderRef.current.get(providerId) ?? modelsRef.current;
    setPendingModelIds((ids) => new Set(ids).add(model.id));
    setFeedback(null);
    try {
      const updated = await setModelEnabled(model.id, !model.enabled);
      const latestProviderModels = modelsByProviderRef.current.get(providerId) ?? providerModels;
      const next = latestProviderModels.map((item) => item.id === updated.id ? updated : item);
      modelsByProviderRef.current.set(providerId, next);
      if (selectedIdRef.current === providerId) {
        modelsRef.current = next;
        setModels(next);
      }
      onUsableModelsChange?.(providerId, enabledProviderIdsRef.current.has(providerId) ? next : [], next);
    } catch { setFeedback({ error: true, message: t("settings.providers.operationFailed") }); }
    finally { setPendingModelIds((ids) => { const next = new Set(ids); next.delete(model.id); return next; }); }
  }

  async function removeProvider() {
    if (!deletingProvider) return;
    const provider = deletingProvider;
    setProviderBusy(true);
    setFeedback(null);
    try {
      await deleteProvider(provider.id);
      enabledProviderIdsRef.current.delete(provider.id);
      const remaining = providers.filter((item) => item.id !== provider.id);
      setProviders(remaining);
      onUsableModelsChange?.(provider.id, []);
      selectProviderId(remaining[0]?.id ?? null);
      if (remaining.length === 0) { modelsRef.current = []; setModels([]); setLoadedProviderId(null); }
      setCreating(remaining.length === 0);
      setDeletingProvider(null);
    } catch { setDeleteError(true); }
    finally { setProviderBusy(false); }
  }

  return (
    <Card aria-labelledby="provider-heading" className="rounded-xl shadow-sm">
      <div className="flex flex-col gap-3 border-b border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div><h2 id="provider-heading" className="text-base font-semibold text-card-foreground">{t("settings.providers.title")}</h2><p className="mt-1 text-sm text-muted-foreground">{t("settings.providers.description")}</p></div>
        <Button type="button" variant="gradient" disabled={providerSaving || providerBusy} onClick={() => setCreating(true)} className="touch-target h-9">{t("settings.providers.create")}</Button>
      </div>
      <div className="grid gap-6 p-5 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <div className="lg:border-r lg:border-border lg:pr-6">
          <h3 className="mb-2 text-xs font-medium text-muted-foreground">{t("settings.providers.list")}</h3>
          {providers.length === 0 ? <p className="rounded-md bg-muted px-3 py-4 text-sm text-muted-foreground">{t("settings.providers.empty")}</p> : <div className="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible">{providers.map((provider) => <button key={provider.id} type="button" disabled={providerSaving || providerBusy} onClick={() => { selectProviderId(provider.id); setCreating(false); setFeedback(null); }} aria-pressed={!creating && selectedId === provider.id} className={`touch-target min-w-40 cursor-pointer rounded-md border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${!creating && selectedId === provider.id ? "border-primary bg-accent text-foreground" : "border-border bg-background text-muted-foreground hover:text-foreground"}`}><span className="block truncate text-sm font-medium">{provider.name}</span><span className="block truncate text-xs">{provider.enabled ? t("common.enabled") : t("common.disabled")}</span></button>)}</div>}
        </div>
        <div className="min-w-0 space-y-5">
          {creating || selected ? <ProviderForm key={creating ? "new" : selected?.id} provider={creating ? null : selected} onSubmit={saveProvider} onCancel={creating && providers.length ? () => setCreating(false) : undefined} onSavingChange={setProviderSaving} /> : null}
          {!creating && selected ? <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold text-card-foreground">{t("settings.providers.models")}</h3><div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={toggleProvider} disabled={providerBusy || providerSaving} aria-busy={providerBusy} className="touch-target h-9">{providerBusy ? <Loader2 className="mr-2 motion-reduce:animate-none" /> : null}{selected.enabled ? t("settings.providers.disableProvider") : t("settings.providers.enableProvider")}</Button>
              <Button type="button" variant="gradient" onClick={syncModels} disabled={providerSaving || syncingId !== null || !selected.enabled} aria-busy={syncingId === selected.id} className="touch-target h-9">{syncingId === selected.id ? <Loader2 className="mr-2 motion-reduce:animate-none" /> : null}{t("settings.providers.sync")}</Button>
              <Button type="button" variant="ghost" onClick={() => { setDeleteError(false); setDeletingProvider(selected); }} disabled={providerBusy || providerSaving} className="touch-target h-9 text-destructive hover:bg-accent">{t("common.delete")}</Button>
            </div></div>
            <ModelList models={models} loading={modelsLoading} disabled={providerSaving} pendingModelIds={pendingModelIds} onToggle={toggleModel} />
          </div> : null}
          {feedback ? (
            <Alert variant={feedback.error ? "destructive" : "success"} role={feedback.error ? "alert" : "status"} className="px-3 py-2 text-sm">
              <AlertDescription>{feedback.message}</AlertDescription>
            </Alert>
          ) : null}
        </div>
      </div>
      <ConfirmDialog open={deletingProvider !== null} busy={providerBusy} destructive loaderClassName="motion-reduce:animate-none" title={t("settings.providers.deleteTitle")} description={t("settings.providers.deleteDescription", { name: deletingProvider?.name ?? "" })} confirmLabel={t("settings.providers.confirmDelete")} cancelLabel={t("common.cancel")} onCancel={() => { setDeletingProvider(null); setDeleteError(false); }} onConfirm={removeProvider}>
        {deleteError ? <p role="alert" className="text-sm text-destructive">{t("settings.providers.deleteFailed")}</p> : null}
      </ConfirmDialog>
    </Card>
  );
}
