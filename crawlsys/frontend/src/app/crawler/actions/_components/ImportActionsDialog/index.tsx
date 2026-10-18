"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useId, useRef, useState } from "react";

import { Feedback } from "../../../_components/Feedback";
import { FormField } from "../../../_components/FormField";
import { SubmitButton } from "../../../_components/SubmitButton";
import { Button } from "@/app/_components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/app/_components/ui/dialog";
import { Select } from "@/app/_components/ui/select";
import { CrawlerApiError, crawlerRequest } from "../../../../../utils/crawler/crawler-api";
import type { ActionImportResponse, Platform } from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";

const MAX_FILE_BYTES = 2 * 1024 * 1024;
const MAX_ACTIONS = 1000;

function positiveSafeInteger(value: FormDataEntryValue | null) {
  if (typeof value !== "string" || !/^\d+$/.test(value)) return;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : undefined;
}

export function ImportActionsDialog({ platforms }: { platforms: Platform[] }) {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [file, setFile] = useState<File>();
  const [feedback, setFeedback] = useState<{ type: "error" | "success"; text: string }>();

  function show() {
    restoreFocusRef.current = document.activeElement as HTMLElement | null;
    setOpen(true);
    setFeedback(undefined);
  }

  function finishClose() {
    setOpen(false);
    setFile(undefined);
    queueMicrotask(() => restoreFocusRef.current?.focus());
  }

  function close() {
    finishClose();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    if (!file) {
      setFeedback({ type: "error", text: t("actions.importChooseFile") });
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setFeedback({ type: "error", text: t("actions.importFileTooLarge") });
      return;
    }
    let actions: unknown;
    try {
      actions = JSON.parse(await file.text());
    } catch {
      setFeedback({ type: "error", text: t("actions.importInvalidFile") });
      return;
    }
    if (!Array.isArray(actions)) {
      setFeedback({ type: "error", text: t("actions.importArrayRequired") });
      return;
    }
    if (actions.length > MAX_ACTIONS) {
      setFeedback({ type: "error", text: t("actions.importLimit") });
      return;
    }
    const platformId = positiveSafeInteger(data.get("platform_id"));
    if (!platformId) {
      setFeedback({ type: "error", text: t("actions.importChoosePlatform") });
      return;
    }
    setLoading(true);
    setFeedback(undefined);
    try {
      const result = await crawlerRequest<ActionImportResponse>("/actions/import", {
        method: "POST",
        body: JSON.stringify({ platform_id: platformId, actions }),
      });
      setFeedback({ type: "success", text: t("actions.importSuccess", { created: result.created_count, updated: result.updated_count }) });
      router.refresh();
    } catch (error) {
      if (error instanceof CrawlerApiError) {
        const firstFieldError = Object.entries(error.fieldErrors)[0];
        setFeedback({
          type: "error",
          text: firstFieldError
            ? t("actions.importFieldError", { field: firstFieldError[0], error: firstFieldError[1] })
            : error.message,
        });
      } else {
        setFeedback({ type: "error", text: t("actions.importUnknownError") });
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Button type="button" variant="outline" onClick={show}>
        {t("actions.import")}
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
            className="w-[min(32rem,calc(100%-2rem))] p-6"
          >
            <DialogHeader>
              <DialogTitle id={titleId}>{t("actions.import")}</DialogTitle>
            </DialogHeader>
            <form onSubmit={submit} className="mt-5 grid gap-4">
              {feedback ? <Feedback variant={feedback.type}>{feedback.text}</Feedback> : null}
              <FormField id="platform_id" label={t("actions.targetPlatform")} required>
                <Select name="platform_id" defaultValue={platforms[0]?.bs_id ?? ""}>
                  {platforms.map((platform) => (
                    <option key={platform.bs_id} value={platform.bs_id}>
                      {platform.bs_name ?? platform.bs_platform_code}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id="file" label={t("actions.jsonFile")} required hint={t("actions.jsonFileHint")}>
                <input
                  name="file"
                  type="file"
                  accept=".json,application/json"
                  onChange={(event) => setFile(event.currentTarget.files?.[0])}
                  className="block w-full cursor-pointer rounded-md border border-input bg-background text-sm text-muted-foreground file:mr-3 file:h-9 file:cursor-pointer file:border-0 file:border-r file:border-input file:bg-secondary file:px-4 file:text-sm file:font-medium file:text-foreground hover:file:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </FormField>
              {file ? (
                <div className="flex items-center justify-between rounded-md border border-border bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
                  <span className="max-w-[280px] truncate font-medium text-foreground">{file.name}</span>
                  <span>{(file.size / 1024).toFixed(1)} KB</span>
                </div>
              ) : null}
              <DialogFooter>
                <Button type="button" variant="outline" disabled={loading} onClick={close}>
                  {t("common.cancel")}
                </Button>
                <SubmitButton loading={loading}>{t("actions.confirmImport")}</SubmitButton>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      ) : null}
    </>
  );
}
