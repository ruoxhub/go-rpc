"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { t, type MessageKey } from "../../i18n";

const navigation = [
  { href: "/analysis", label: "nav.analysis" },
  { href: "/crawler/platforms", label: "nav.platforms" },
  { href: "/crawler/actions", label: "nav.actions" },
  { href: "/crawler/keywords", label: "nav.keywords" },
  { href: "/crawler/tasks", label: "nav.tasks" },
  { href: "/crawler/datatypes", label: "nav.datatypes" },
  { href: "/settings", label: "nav.settings" },
] satisfies Array<{ href: string; label: MessageKey }>;

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav aria-label={t("nav.main")}>
      <ul className="space-y-1">
        {navigation.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={`touch-target relative block rounded-md px-3 py-2 text-sm transition-colors ${
                  active
                    ? "bg-sidebar-accent font-medium text-primary"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground"
                }`}
              >
                {active ? (
                  <span
                    className="absolute inset-y-1 left-0 w-0.5 bg-gradient-back"
                    aria-hidden="true"
                  />
                ) : null}
                {t(item.label)}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
