"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useId, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";

import { Feedback } from "../../../_components/Feedback";
import { FormField } from "../../../_components/FormField";
import { SubmitButton } from "../../../_components/SubmitButton";
import { Button } from "@/app/_components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/app/_components/ui/dialog";
import { Select } from "@/app/_components/ui/select";
import { Switch } from "@/app/_components/ui/switch";
import { CrawlerApiError, crawlerRequest } from "../../../../../utils/crawler/crawler-api";
import type { ActionSyncResponse, Platform } from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";

export interface SyncActionsDialogProps {
  platforms: Platform[];
  defaultPlatformId?: string;
}

export function SyncActionsDialog({ platforms, defaultPlatformId }: SyncActionsDialogProps) {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [platformId, setPlatformId] = useState<string>(defaultPlatformId ?? "");
  const [force, setForce] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "error" | "success"; text: string }>();
  const [result, setResult] = useState<ActionSyncResponse>();

  function show() {
    restoreFocusRef.current = document.activeElement as HTMLElement | null;
    setOpen(true);
    setFeedback(undefined);
    setResult(undefined);
    setPlatformId(defaultPlatformId ?? "");
  }

  function finishClose() {
    setOpen(false);
    setResult(undefined);
    queueMicrotask(() => restoreFocusRef.current?.focus());
  }

  function close() {
    finishClose();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setFeedback(undefined);
    setResult(undefined);

    try {
      const payload = {
        platform_id: platformId ? Number(platformId) : undefined,
        force,
      };
      const data = await crawlerRequest<ActionSyncResponse>("/actions/sync", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setResult(data);
      const summaryText =
        data.total_synced > 0 || data.skipped_manual_count > 0
          ? t("actions.syncSuccess", {
              inserted: data.inserted_count,
              updated: data.updated_count,
              skipped: data.skipped_manual_count,
            })
          : t("actions.syncEmpty");

      setFeedback({ type: "success", text: summaryText });
      router.refresh();
    } catch (error) {
      if (error instanceof CrawlerApiError) {
        setFeedback({ type: "error", text: error.message });
      } else {
        setFeedback({ type: "error", text: t("actions.syncUnknownError") });
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        onClick={show}
        className="gap-1.5"
      >
        <RefreshCw className="size-4" aria-hidden="true" />
        {t("actions.sync")}
      </Button>

      {open ? (
        <Dialog open={open} onOpenChange={(isOpen) => !isOpen && !loading && close()}>
          <DialogContent
            ref={dialogRef}
            aria-labelledby={titleId}
            onCancel={(event) => {
              event.preventDefault();
              if (!loading) close();
            }}
            showCloseButton={!loading}
            className="w-[min(34rem,calc(100%-2rem))] p-6"
          >
            <DialogHeader>
              <DialogTitle id={titleId}>
                {t("actions.syncTitle")}
              </DialogTitle>
              <DialogDescription>
                {t("actions.syncDescription")}
              </DialogDescription>
            </DialogHeader>

            <form onSubmit={submit} className="mt-5 grid gap-4">
              {feedback ? <Feedback variant={feedback.type}>{feedback.text}</Feedback> : null}

              <FormField id="sync_platform_id" label={t("actions.syncPlatformLabel")}>
                <Select
                  id="sync_platform_id"
                  name="platform_id"
                  value={platformId}
                  onChange={(e) => setPlatformId(e.target.value)}
                >
                  <option value="">{t("actions.syncAllPlatforms")}</option>
                  {platforms.map((platform) => (
                    <option key={platform.bs_id} value={platform.bs_id}>
                      {platform.bs_name ?? platform.bs_platform_code}
                    </option>
                  ))}
                </Select>
              </FormField>

              <label className="flex cursor-pointer items-start justify-between gap-3 rounded-md border border-border bg-muted/20 p-3 text-sm">
                <div className="grid gap-0.5">
                  <span className="font-medium text-foreground">{t("actions.syncForceLabel")}</span>
                  <span className="text-xs text-muted-foreground">{t("actions.syncForceHint")}</span>
                </div>
                <Switch
                  name="force"
                  aria-label={t("actions.syncForceLabel")}
                  checked={force}
                  onCheckedChange={setForce}
                />
              </label>

              {result?.details && result.details.length > 0 ? (
                <div className="max-h-48 overflow-y-auto rounded-md border border-border bg-muted/40 p-3">
                  <div className="mb-2 text-xs font-medium text-foreground">
                    {t("actions.syncDetailsTitle")} ({result.details.length})
                  </div>
                  <div className="grid gap-1.5 text-xs">
                    {result.details.map((detail, idx) => (
                      <div
                        key={`${detail.platform}-${detail.action}-${idx}`}
                        className="flex items-center justify-between gap-2 border-b border-border/40 pb-1 last:border-0 last:pb-0"
                      >
                        <span className="font-mono font-medium text-foreground">
                          {detail.platform}/{detail.action}
                        </span>
                        <span
                          className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                            detail.status === "inserted"
                              ? "bg-success/15 text-success-strong"
                              : detail.status === "updated"
                              ? "bg-info/15 text-info-strong"
                              : "bg-muted text-muted-foreground"
                          }`}
                        >
                          {detail.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {result?.unknown_groups && result.unknown_groups.length > 0 ? (
                <div className="text-xs text-muted-foreground">
                  {t("actions.syncUnknownGroups", { groups: result.unknown_groups.join(", ") })}
                </div>
              ) : null}

              <DialogFooter className="pt-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={loading}
                  onClick={close}
                >
                  {t("common.cancel")}
                </Button>
                <SubmitButton loading={loading}>{t("actions.startSync")}</SubmitButton>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      ) : null}
    </>
  );
}
