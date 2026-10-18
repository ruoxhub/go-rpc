import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "./_components/AppShell";
import { getAppLocale, t } from "./i18n";
import "./globals.css";

export const metadata: Metadata = {
  title: t("app.title"),
  description: t("app.subtitle"),
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang={getAppLocale()}>
      <body className="bg-background font-sans text-foreground">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
