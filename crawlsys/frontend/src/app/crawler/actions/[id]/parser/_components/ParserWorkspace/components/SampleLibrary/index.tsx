// SampleLibrary：管理当前 Action 的脱敏样例元数据和分页。
"use client";

import { useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { deleteParserSample, listParserSamples } from "@/api/action-parser/action-parser.api";
import { CrawlerApiError } from "@/utils/crawler/crawler-api";
import { t } from "@/app/i18n";
import { ConfirmDialog } from "@/app/_components/ConfirmDialog";
import { Button } from "@/app/_components/ui/button";
import { Card } from "@/app/_components/ui/card";
import { SampleInspector } from "../SampleInspector";
import { useParserWorkspace } from "../../index";

export function SampleLibrary() {
  const { action, samples, sampleServerCount, samplesExhausted, appendSamples, replaceSamplesFromServer, removeSample, setActiveSample, activeSampleId, selectedSampleIds, toggleSelectedSample } = useParserWorkspace(useShallow((state) => ({
    action: state.action,
    samples: state.samples,
    sampleServerCount: state.sampleServerCount,
    samplesExhausted: state.samplesExhausted,
    appendSamples: state.appendSamples,
    replaceSamplesFromServer: state.replaceSamplesFromServer,
    removeSample: state.removeSample,
    setActiveSample: state.setActiveSample,
    activeSampleId: state.activeSampleId,
    selectedSampleIds: state.selectedSampleIds,
    toggleSelectedSample: state.toggleSelectedSample,
  })));
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [needsReconcile, setNeedsReconcile] = useState(false);

  async function reload() {
    try {
      const page = await listParserSamples(action.ba_id, { offset: 0, limit: 20 });
      replaceSamplesFromServer(page.items);
      setNeedsReconcile(false);
    } catch (error) {
      setFeedback(error instanceof CrawlerApiError ? error.message : t("parser.sample.listUnknownError"));
    }
  }

  async function loadMore() {
    const page = await listParserSamples(action.ba_id, { offset: sampleServerCount, limit: 20 });
    appendSamples(page.items, sampleServerCount + page.items.length, page.items.length < 20);
  }

  async function remove() {
    if (deleteId === null) return;
    setBusy(true);
    try {
      await deleteParserSample(action.ba_id, deleteId);
      removeSample(deleteId);
      setDeleteId(null);
      await reload();
    } catch (error) {
      if (error instanceof CrawlerApiError && error.code === "sample_in_use") setFeedback(error.message);
      else if (error instanceof CrawlerApiError && error.status === 404) { removeSample(deleteId); setDeleteId(null); await reload(); }
      else setFeedback(error instanceof CrawlerApiError ? error.message : t("parser.sample.deleteUnknownError"));
    } finally { setBusy(false); }
  }

  return (
    <section className="grid gap-4" aria-label={t("parser.section.samples")}>
      <Card className="grid gap-3 p-4 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-foreground">{t("parser.section.samples")}</h2>
          {selectedSampleIds.length > 0 ? (
            <span className="text-xs text-muted-foreground">
              {t("parser.sample.selected", { count: selectedSampleIds.length })}
            </span>
          ) : null}
        </div>
        {feedback ? <p role="alert" className="text-sm text-destructive">{feedback}</p> : null}
        {samples.length === 0 ? <p className="text-sm text-muted-foreground">{t("parser.samples.empty")}</p> : (
          <ul className="grid gap-2">
            {samples.map((sample) => (
              <li key={sample.sample_id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={`${t("parser.section.samples")} #${sample.sample_id}`}
                    checked={selectedSampleIds.includes(sample.sample_id)}
                    onChange={() => toggleSelectedSample(sample.sample_id)}
                    className="size-4 cursor-pointer accent-primary"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setActiveSample(sample.sample_id)}
                    className="min-h-11 justify-start px-2 text-left text-sm font-normal text-foreground"
                  >
                    #{sample.sample_id} · {sample.response_bytes} bytes · {sample.rpc_duration_ms} ms
                  </Button>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setDeleteId(sample.sample_id)}
                  className="min-h-11 px-3 text-destructive hover:bg-destructive/10 hover:text-destructive"
                >
                  {t("common.delete")}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {needsReconcile ? (
          <Button type="button" variant="link" onClick={() => void reload()} className="min-h-11 justify-start px-0 text-primary">
            {t("parser.sample.resync")}
          </Button>
        ) : null}
        {!samplesExhausted && !needsReconcile ? (
          <Button type="button" variant="outline" onClick={() => void loadMore()} className="min-h-11 px-3">
            {t("parser.sample.loadMore")}
          </Button>
        ) : null}
      </Card>
      {activeSampleId !== null ? <SampleInspector /> : null}
      <ConfirmDialog open={deleteId !== null} title={t("parser.sample.deleteTitle")} description={t("parser.sample.deleteDescription")} confirmLabel={t("common.delete")} cancelLabel={t("common.cancel")} destructive busy={busy} onCancel={() => setDeleteId(null)} onConfirm={() => void remove()} />
    </section>
  );
}
