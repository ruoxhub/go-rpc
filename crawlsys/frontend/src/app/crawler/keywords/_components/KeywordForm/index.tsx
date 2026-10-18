"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Feedback } from "../../../_components/Feedback";
import { FormField } from "../../../_components/FormField";
import { SubmitButton } from "../../../_components/SubmitButton";
import { Button } from "../../../../_components/ui/button";
import { Card } from "../../../../_components/ui/card";
import { Input } from "../../../../_components/ui/input";
import { Select } from "../../../../_components/ui/select";
import { CrawlerApiError, crawlerRequest } from "../../../../../utils/crawler/crawler-api";
import type { Keyword, KeywordPayload, Platform } from "../../../../../utils/crawler/crawler-types";
import { t } from "../../../../i18n";

interface KeywordFormProps {
  mode: "create" | "edit";
  platforms: Platform[];
  keyword?: Keyword;
}

function platformLabel(platform: Platform) {
  const name = platform.bs_name ?? platform.bs_platform_code ?? t("keywords.platformName", { id: platform.bs_id });
  if (platform.bs_status === "D") return t("keywords.deletedPlatform", { name });
  if (platform.bs_status === "0") return t("keywords.disabledPlatform", { name });
  return name;
}

export function KeywordForm({ mode, platforms, keyword }: KeywordFormProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<string>();
  const currentPlatform = keyword
    ? platforms.find((platform) => platform.bs_platform_code === keyword.platform)
    : undefined;
  const historicalPlatform = mode === "edit" && (!currentPlatform || currentPlatform.bs_status !== "1");
  const [selectedPlatform, setSelectedPlatform] = useState(
    historicalPlatform ? "" : keyword?.platform ?? platforms[0]?.bs_platform_code ?? "",
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPlatform) return;
    setLoading(true);
    setFieldErrors({});
    setFeedback(undefined);
    const data = new FormData(event.currentTarget);
    const payload: KeywordPayload = {
      platform: String(data.get("platform") ?? ""),
      keyword: String(data.get("keyword") ?? "").trim(),
    };
    try {
      await crawlerRequest<Keyword>(mode === "edit" ? `/keywords/${keyword?.id}` : "/keywords", {
        method: mode === "edit" ? "PUT" : "POST",
        body: JSON.stringify(payload),
      });
      router.push("/crawler/keywords");
    } catch (error) {
      if (error instanceof CrawlerApiError) {
        setFieldErrors(error.fieldErrors);
        if (error.kind !== "validation") setFeedback(error.message);
      } else {
        setFeedback(t("keywords.saveUnknownError"));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="p-6 shadow-sm">
      <form onSubmit={submit} className="grid gap-5">
        {feedback ? <Feedback variant="error">{feedback}</Feedback> : null}
        {historicalPlatform && !selectedPlatform ? (
          <Feedback variant="warning">{t("keywords.platformUnavailableWarning")}</Feedback>
        ) : null}
        {historicalPlatform ? (
          <FormField id="platform_readonly" label={t("keywords.currentPlatform")}>
            <p className="flex h-9 items-center rounded-md border border-border bg-muted px-3 text-sm text-muted-foreground">
              {currentPlatform ? platformLabel(currentPlatform) : t("keywords.platformUnavailable", { platform: keyword!.platform })}
            </p>
          </FormField>
        ) : null}
        <FormField id="platform" label={t("keywords.platform")} required error={fieldErrors.platform}>
          <Select name="platform" value={selectedPlatform} onChange={(event) => setSelectedPlatform(event.target.value)} className="bg-background">
            {historicalPlatform ? <option value="">{t("keywords.choosePlatform")}</option> : null}
            {platforms.filter((platform) => platform.bs_status === "1" && platform.bs_platform_code).map((platform) => (
              <option key={platform.bs_id} value={platform.bs_platform_code!}>{platformLabel(platform)}</option>
            ))}
          </Select>
        </FormField>
        <FormField id="keyword" label={t("keywords.name")} required error={fieldErrors.keyword}>
          <Input name="keyword" defaultValue={keyword?.keyword ?? ""} maxLength={1000} className="bg-background" />
        </FormField>
        <div className="flex justify-end gap-2">
          <Link href="/crawler/keywords" className="touch-target inline-flex h-9 cursor-pointer items-center rounded-md border border-border bg-background px-4 text-sm font-medium hover:bg-accent">
            {t("common.cancel")}
          </Link>
          <SubmitButton loading={loading} disabled={!selectedPlatform}>{mode === "create" ? t("keywords.create") : t("common.save")}</SubmitButton>
        </div>
      </form>
    </Card>
  );
}
