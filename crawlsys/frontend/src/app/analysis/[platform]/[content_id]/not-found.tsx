import Link from "next/link";
import { t } from "../../../i18n";
export default function AnalysisNotFound() { return <main className="grid min-h-96 place-items-center text-center"><div><h1 className="text-2xl font-semibold">{t("analysis.empty.title")}</h1><Link className="mt-4 inline-block text-sm font-medium text-primary hover:underline" href="/analysis">{t("analysis.detail.back")}</Link></div></main>; }
