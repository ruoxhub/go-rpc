// StatusOverview：展示发布、草稿、未保存修改和校验报告四类真实状态。
import type {
  ParserPreviewReport,
  ParserRevision,
} from "@/api/action-parser/action-parser.types";
import { t } from "../../../../../../../../i18n";

import { Badge } from "@/app/_components/ui";
import { Card } from "@/app/_components/ui/card";

interface StatusOverviewProps {
  published: ParserRevision | null;
  draft: ParserRevision | null;
  dirty: boolean;
  previewReport: ParserPreviewReport | null;
  sampleCount?: number;
}

function StatusCard({
  title,
  value,
  badge,
}: {
  title: string;
  value: string;
  badge: React.ReactNode;
}) {
  return (
    <Card className="flex flex-col justify-between p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {title}
        </h2>
        {badge}
      </div>
      <p className="mt-2 text-sm font-medium text-foreground">{value}</p>
    </Card>
  );
}

export function StatusOverview({
  published,
  draft,
  dirty,
  previewReport,
  sampleCount = 0,
}: StatusOverviewProps) {
  const steps = [
    {
      num: 1,
      title: "获取样例",
      desc: sampleCount > 0 ? `已就绪 (${sampleCount} 个样例)` : "待获取数据",
      done: sampleCount > 0,
      current: sampleCount === 0,
    },
    {
      num: 2,
      title: "制定规则",
      desc: draft ? `草稿 #${draft.revision_no}` : "待创建草稿",
      done: draft !== null,
      current: sampleCount > 0 && draft === null,
    },
    {
      num: 3,
      title: "校验预览",
      desc: previewReport
        ? previewReport.passed
          ? "校验通过"
          : "校验未通过"
        : "待运行校验",
      done: previewReport?.passed === true,
      current: draft !== null && (!previewReport || !previewReport.passed),
    },
    {
      num: 4,
      title: "生产发布",
      desc: published ? `版本 #${published.revision_no} 运行中` : "待上线",
      done: published !== null,
      current: previewReport?.passed === true && published === null,
    },
  ];

  return (
    <div className="grid gap-3">
      {/* 工作流引导横条 */}
      <Card
        aria-label="配置工作流程"
        className="grid grid-cols-2 gap-2 bg-card/60 p-3 shadow-sm lg:grid-cols-4"
      >
        {steps.map((step) => (
          <div
            key={step.num}
            className={`flex items-center gap-3 rounded-md px-3 py-2 transition-colors ${
              step.done
                ? "bg-success/5 text-foreground"
                : step.current
                  ? "bg-primary/10 text-foreground ring-1 ring-primary/20"
                  : "text-muted-foreground opacity-70"
            }`}
          >
            <span
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                step.done
                  ? "bg-success text-white"
                  : step.current
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground"
              }`}
            >
              {step.done ? "✓" : step.num}
            </span>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 text-xs font-semibold">
                <span>{step.title}</span>
                {step.current ? (
                  <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                ) : null}
              </div>
              <p className="truncate text-[11px] text-muted-foreground">
                {step.desc}
              </p>
            </div>
          </div>
        ))}
      </Card>

      {/* 状态卡片 */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatusCard
          title={t("parser.status.production.title")}
          value={
            published
              ? t("parser.status.production.configured", {
                  revision: published.revision_no,
                })
              : t("parser.status.notConfigured")
          }
          badge={
            published ? (
              <Badge variant="success">已上线</Badge>
            ) : (
              <Badge variant="muted">未配置</Badge>
            )
          }
        />
        <StatusCard
          title={t("parser.status.draft.title")}
          value={
            draft
              ? t("parser.status.draft.configured", {
                  revision: draft.revision_no,
                })
              : t("parser.status.notConfigured")
          }
          badge={
            draft ? (
              <Badge variant="info">编辑中</Badge>
            ) : (
              <Badge variant="muted">未配置</Badge>
            )
          }
        />
        <StatusCard
          title={t("parser.status.dirty.title")}
          value={
            dirty
              ? t("parser.status.dirty.unsaved")
              : t("parser.status.dirty.saved")
          }
          badge={
            dirty ? (
              <Badge variant="warning">未保存</Badge>
            ) : (
              <Badge variant="muted">已同步</Badge>
            )
          }
        />
        <StatusCard
          title={t("parser.status.report.title")}
          value={
            previewReport
              ? previewReport.passed
                ? t("parser.status.report.passed")
                : t("parser.status.report.failed")
              : t("parser.status.report.unavailable")
          }
          badge={
            previewReport ? (
              previewReport.passed ? (
                <Badge variant="success">通过</Badge>
              ) : (
                <Badge variant="destructive">未通过</Badge>
              )
            ) : (
              <Badge variant="muted">无报告</Badge>
            )
          }
        />
      </div>
    </div>
  );
}
