import type { ReactNode } from "react";
import { t } from "../../i18n";

import { MobileNav } from "../MobileNav";
import { SidebarNav } from "../SidebarNav";
import { Separator } from "../ui/separator";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen md:grid md:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="hidden border-r border-border bg-sidebar md:block">
        <div className="sticky top-0 flex h-screen flex-col px-3 py-5">
          <Brand />
          <Separator className="mb-4" />
          <SidebarNav />
        </div>
      </aside>

      <div className="min-w-0">
        <header className="border-b border-border bg-sidebar px-4 py-3 md:hidden">
          <MobileNav brand={<Brand />} />
        </header>
        {children}
      </div>
    </div>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2 px-2 pb-3">
      <span
        className="h-2 w-2 rounded-full bg-gradient-back"
        aria-hidden="true"
      />
      <div>
        <p className="text-sm font-semibold">{t("app.title")}</p>
        <p className="text-xs text-muted-foreground">{t("app.subtitle")}</p>
      </div>
    </div>
  );
}
