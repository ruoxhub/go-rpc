"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import { usePathname } from "next/navigation";
import { t } from "../../i18n";

import { SidebarNav } from "../SidebarNav";

export function MobileNav({ brand }: { brand?: ReactNode }) {
  const pathname = usePathname();
  const [openPathname, setOpenPathname] = useState<string | null>(null);
  const open = openPathname === pathname;

  return (
    <details open={open}>
      <summary
        onClick={(event) => {
          event.preventDefault();
          setOpenPathname(open ? null : pathname);
        }}
        className="flex cursor-pointer list-none items-center justify-between rounded-md focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        {brand}
        <span className="text-xs font-medium text-muted-foreground">{t("nav.menu")}</span>
      </summary>
      <div className="pt-3">
        <SidebarNav onNavigate={() => setOpenPathname(null)} />
      </div>
    </details>
  );
}
