import type { Locale } from "./index";

/** Từ điển của một khu: cùng một cấu trúc cho mỗi ngôn ngữ. */
export type Dict<T> = Record<Locale, T>;

/**
 * Khai báo chuỗi giao diện của một khu (một file `messages.ts` cạnh component).
 * Bản `en` phải có đúng các khoá của bản `vi` (TypeScript báo lỗi nếu thiếu hay thừa), nên không sót chuỗi khi dịch.
 * Chuỗi có tham số viết thành hàm, ví dụ `count: (n: number) => \`${n} hồ sơ\``.
 */
export function defineMessages<T>(vi: T, en: NoInfer<T>): Dict<T> {
  return { vi, en };
}
