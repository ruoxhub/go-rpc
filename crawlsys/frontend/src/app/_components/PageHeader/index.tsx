import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  description?: string;
  children?: ReactNode;
}

export function PageHeader({ title, description, children }: PageHeaderProps) {
  return (
    <header className="border-b border-border">
      <div className="flex flex-wrap items-start justify-between gap-4 py-5">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            {title}
          </h1>
          {description ? (
            <p className="mt-1 text-sm text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {children ? <div className="flex items-center gap-2">{children}</div> : null}
      </div>
      <div aria-hidden className="h-px bg-gradient-back" />
    </header>
  );
}
