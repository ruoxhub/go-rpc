import { PageHeader } from "../_components/PageHeader";
import { t } from "../i18n";
import { SettingsClient } from "./_components/SettingsClient";
import { getSettings, listProviders, loadProviderModelCatalog } from "./utils/settings-api";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const [settings, providers] = await Promise.all([getSettings(), listProviders()]);
  const { catalog, models, incomplete } = await loadProviderModelCatalog(providers);
  return <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 md:px-6 md:py-8"><PageHeader title={t("settings.title")} description={t("settings.description")}/><SettingsClient initialSettings={settings} initialProviders={providers} initialModels={models} initialModelCatalog={catalog} modelCatalogIncomplete={incomplete}/></main>;
}
