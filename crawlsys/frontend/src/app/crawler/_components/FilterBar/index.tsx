import type { ReactNode } from "react";
import { Card } from "@/app/_components/ui/card";

interface FilterBarProps {
  children: ReactNode;
  actions?: ReactNode;
  "aria-label": string;
}

export function FilterBar({
  children,
  actions,
  "aria-label": ariaLabel,
}: FilterBarProps) {
  return (
    <Card
      role="search"
      aria-label={ariaLabel}
      className="flex flex-wrap items-end justify-between gap-3 p-4 shadow-sm"
    >
      <div className="flex flex-1 flex-wrap items-end gap-3">{children}</div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </Card>
  );
}
