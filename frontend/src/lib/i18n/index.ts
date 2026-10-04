import en from "./en";
import vi, { type Messages } from "./vi";

export type Locale = "vi" | "en";
export const LOCALES: readonly Locale[] = ["vi", "en"];
export const DEFAULT_LOCALE: Locale = "vi";
export const LOCALE_COOKIE = "locale";

const catalog: Record<Locale, Messages> = { vi, en };

export function isLocale(value: string | undefined | null): value is Locale {
  return value === "vi" || value === "en";
}

export function getMessages(locale: Locale): Messages {
  return catalog[locale];
}

/** Thay {tên} trong chuỗi bằng giá trị tương ứng. */
export function format(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => values[key] ?? `{${key}}`);
}

export type { Messages };
