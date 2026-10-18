// ParserLoading：解析器页面的三段式加载骨架。
import { t } from "../../../../i18n";

const sections = [
  { label: t("parser.loading.status"), height: "h-28" },
  { label: t("parser.loading.workspace"), height: "h-80" },
  { label: t("parser.loading.history"), height: "h-40" },
];

export default function ParserLoading() {
  return (
    <main
      aria-busy="true"
      className="mx-auto grid w-full max-w-7xl gap-4 px-4 py-6 lg:px-8"
    >
      {sections.map((section) => (
        <section
          key={section.label}
          role="status"
          aria-label={section.label}
          className={`rounded-lg border border-border bg-muted ${section.height}`}
        />
      ))}
    </main>
  );
}
