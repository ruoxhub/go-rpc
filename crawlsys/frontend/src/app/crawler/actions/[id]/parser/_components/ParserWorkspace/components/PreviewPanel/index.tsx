// PreviewPanel：展示最近一次校验报告的状态、统计、错误和预览记录。
"use client";

import { useShallow } from "zustand/react/shallow";

import { Badge } from "@/app/_components/ui";
import { Card } from "@/app/_components/ui/card";
import { t } from "@/app/i18n";
import { JsonTree } from "../JsonTree";
import { useParserWorkspace } from "../../index";

export function PreviewPanel() {
  const { previewReport } = useParserWorkspace(
    useShallow((state) => ({ previewReport: state.previewReport })),
  );

  if (!previewReport) {
    return (
      <Card
        className="grid gap-3 p-5 shadow-sm"
        aria-label={t("parser.report.title")}
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
          <div>
            <h3 className="font-semibold text-foreground">{t("parser.report.title")}</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              校验解析规则对样例数据的提取效果，验证字段提取准确率与结构合规性。
            </p>
          </div>
          <Badge variant="muted">暂未运行</Badge>
        </div>
        <div className="rounded-md border border-dashed border-border bg-muted/20 p-6 text-center">
          <p className="text-sm font-medium text-foreground">
            {t("parser.report.unavailable")}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            配置或修改完解析规则后，请在上方控制条点击【运行预览】生成最新校验报告与数据提取视图。
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card
      className="grid gap-4 p-5 shadow-sm"
      aria-label={t("parser.report.title")}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
        <div>
          <h3 className="font-semibold text-foreground">{t("parser.report.title")}</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            最近一次解析规则对样例数据的提取校验统计与结构预览。
          </p>
        </div>
        <Badge variant={previewReport.passed ? "success" : "destructive"}>
          {previewReport.passed
            ? t("parser.report.passed")
            : t("parser.report.failed")}
        </Badge>
      </div>
      <dl className="grid grid-cols-3 gap-2 text-sm">
        <div className="rounded-md bg-muted px-3 py-2">
          <dt className="text-xs text-muted-foreground">
            {t("parser.report.sourceRecords")}
          </dt>
          <dd className="font-numeric tabular-nums">{previewReport.source_records}</dd>
        </div>
        <div className="rounded-md bg-muted px-3 py-2">
          <dt className="text-xs text-muted-foreground">
            {t("parser.report.validRecords")}
          </dt>
          <dd className="font-numeric tabular-nums">{previewReport.valid_records}</dd>
        </div>
        <div className="rounded-md bg-muted px-3 py-2">
          <dt className="text-xs text-muted-foreground">
            {t("parser.report.invalidRecords")}
          </dt>
          <dd className="font-numeric tabular-nums">{previewReport.invalid_records}</dd>
        </div>
      </dl>

      {previewReport.errors.length > 0 ? (
        <div className="grid gap-1">
          <h4 className="text-xs font-medium text-muted-foreground">
            {t("parser.report.errors")}
          </h4>
          <ul className="grid gap-1 text-sm text-foreground">
            {previewReport.errors.map((error, index) => (
              <li key={index} className="font-mono text-xs">
                #{error.record_index} {error.target ?? "-"} · {error.code}
              </li>
            ))}
          </ul>
          {previewReport.errors_truncated ? (
            <p className="text-xs text-muted-foreground">
              {t("parser.report.errorsTruncated")}
            </p>
          ) : null}
        </div>
      ) : null}

      {previewReport.preview.length > 0 ? (
        <div className="grid gap-1">
          <h4 className="text-xs font-medium text-muted-foreground">
            {t("parser.report.preview")}
          </h4>
          <div className="max-h-72 overflow-auto rounded-md border border-border p-2">
            <JsonTree value={previewReport.preview[0]} onSelect={() => undefined} />
          </div>
        </div>
      ) : null}
    </Card>
  );
}