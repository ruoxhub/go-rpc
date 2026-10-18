import type { ReactNode } from "react";
import { Badge as ShadcnBadge } from "./ui/badge";
import { Card } from "./ui/card";
import { cn } from "@/utils/cn";

/** 页面区块卡片：display 级标题 + 24px 内边距 + 近乎无阴影 */
export function SectionCard({
  title,
  description,
  extra,
  children,
  className,
}: {
  title: string;
  description?: string;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("p-6 shadow-sm", className)}>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-2xl font-semibold leading-none tracking-[-0.01em]">
            {title}
          </h2>
          {description ? (
            <p className="mt-2 text-xs text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {extra}
      </div>
      {children}
    </Card>
  );
}

type BadgeVariant =
  | "muted"
  | "outline"
  | "primary"
  | "solid-primary"
  | "gradient"
  | "success"
  | "warning"
  | "info"
  | "destructive";

export function Badge({
  variant = "muted",
  children,
  className,
}: {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
}) {
  return (
    <ShadcnBadge variant={variant} className={className}>
      {children}
    </ShadcnBadge>
  );
}

/** 标签 / 关键词 chip（中性 surface） */
export function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md bg-muted px-2 py-1 text-xs leading-4">
      {children}
    </span>
  );
}

export function ChipList({ items }: { items?: (string | undefined)[] }) {
  const list = (items ?? []).filter((item): item is string => Boolean(item));
  if (list.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {list.map((item, index) => (
        <Chip key={`${item}-${index}`}>{item}</Chip>
      ))}
    </div>
  );
}

/** 字段块：小标签 + 内容，用于卡片内部的信息分组 */
export function Field({
  label,
  children,
  className,
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="mb-1 text-xs font-medium text-muted-foreground">
        {label}
      </div>
      <div className="text-sm leading-6">{children}</div>
    </div>
  );
}

/** 键值行（dl 语义） */
export function KeyValue({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <dt className="shrink-0 text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right text-sm">{children}</dd>
    </div>
  );
}

/** 关键指标小卡片 */
export function StatCard({
  label,
  value,
  suffix,
}: {
  label: string;
  value: string;
  suffix?: string;
}) {
  return (
    <Card className="p-4 shadow-sm">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1.5 font-numeric text-2xl font-semibold leading-none tabular-nums">
        {value}
        {suffix ? (
          <span className="ml-0.5 text-sm font-normal text-muted-foreground">
            {suffix}
          </span>
        ) : null}
      </div>
    </Card>
  );
}
