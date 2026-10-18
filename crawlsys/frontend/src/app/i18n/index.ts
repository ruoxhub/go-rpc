import { en } from "./messages/en";
import { zhCN } from "./messages/zh-CN";

export const supportedLocales = ["zh-CN", "en"] as const;
export type AppLocale = (typeof supportedLocales)[number];
export type MessageKey = keyof typeof zhCN;

const locale: AppLocale = process.env.NEXT_PUBLIC_APP_LOCALE === "en" ? "en" : "zh-CN";
const messages: Record<MessageKey, string> = locale === "en" ? en : zhCN;

export function getAppLocale() {
  return locale;
}

export function t(key: MessageKey, params: Record<string, string | number> = {}) {
  return Object.entries(params).reduce(
    (message, [name, value]) => message.replaceAll(`{${name}}`, String(value)),
    messages[key],
  );
}
