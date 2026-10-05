/** Định dạng hiển thị theo ngôn ngữ giao diện. Các hàm thuần, không phụ thuộc trạng thái.
 *
 * Trong component dùng `useFormat()` (components/providers) để lấy bộ định dạng đúng ngôn ngữ đang chọn.
 * Các hàm `fmt*` export ở cuối là bản tiếng Việt, giữ cho mã cũ và nơi không có ngữ cảnh ngôn ngữ.
 */
import type { Locale } from "./i18n";

const INTL_LOCALE: Record<Locale, string> = { vi: "vi-VN", en: "en-US" };

export interface Formatters {
  dateTime: (iso?: string | null) => string;
  date: (iso?: string | null) => string;
  number: (n?: number | null) => string;
  vnd: (n?: number | null) => string;
  /** Số tiền rút gọn cho ô thống kê hẹp: 11,7 tỷ ₫ / 19,6 triệu ₫ (en: 11.7B ₫ / 19.6M ₫). */
  vndCompact: (n?: number | null) => string;
  usd: (n?: number | null) => string;
  pct: (ratio?: number | null, digits?: number) => string;
  score: (score?: number | null) => string;
  /** Thời gian tương đối ngắn gọn ("3 phút trước" / "3 min ago"). */
  ago: (iso: string, now?: Date) => string;
}

const AGO: Record<Locale, { now: string; min: (n: number) => string; hour: (n: number) => string; day: (n: number) => string }> = {
  vi: { now: "vừa xong", min: (n) => `${n} phút trước`, hour: (n) => `${n} giờ trước`, day: (n) => `${n} ngày trước` },
  en: {
    now: "just now",
    min: (n) => `${n} min ago`,
    hour: (n) => `${n} h ago`,
    day: (n) => (n === 1 ? "1 day ago" : `${n} days ago`),
  },
};

const cache = new Map<Locale, Formatters>();

export function formatters(locale: Locale): Formatters {
  const hit = cache.get(locale);
  if (hit) return hit;
  const tag = INTL_LOCALE[locale];
  const dateTime = new Intl.DateTimeFormat(tag, { dateStyle: "short", timeStyle: "short" });
  const dateOnly = new Intl.DateTimeFormat(tag, { dateStyle: "medium" });
  const number = new Intl.NumberFormat(tag);
  const vnd = new Intl.NumberFormat(tag, { style: "currency", currency: "VND", maximumFractionDigits: 0 });
  const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
  const ago = AGO[locale];
  const date = (iso?: string | null) => (iso ? dateOnly.format(new Date(iso)) : "—");
  const f: Formatters = {
    dateTime: (iso) => (iso ? dateTime.format(new Date(iso)) : "—"),
    date,
    number: (n) => (n == null ? "—" : number.format(n)),
    vnd: (n) => (n == null ? "—" : vnd.format(n)),
    vndCompact(n) {
      if (n == null) return "—";
      const abs = Math.abs(n);
      const trim = (x: number) => x.toLocaleString(tag, { maximumFractionDigits: 1 });
      if (abs >= 1e9) return locale === "vi" ? `${trim(n / 1e9)} tỷ ₫` : `${trim(n / 1e9)}B ₫`;
      if (abs >= 1e6) return locale === "vi" ? `${trim(n / 1e6)} triệu ₫` : `${trim(n / 1e6)}M ₫`;
      return vnd.format(n);
    },
    usd: (n) => (n == null ? "—" : usd.format(n)),
    pct: (ratio, digits = 0) => (ratio == null ? "—" : `${(ratio * 100).toFixed(digits)}%`),
    score: (score) => (score == null ? "—" : score.toFixed(1)),
    ago(iso, now = new Date()) {
      const seconds = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 1000));
      if (seconds < 60) return ago.now;
      const minutes = Math.floor(seconds / 60);
      if (minutes < 60) return ago.min(minutes);
      const hours = Math.floor(minutes / 60);
      if (hours < 24) return ago.hour(hours);
      const days = Math.floor(hours / 24);
      return days < 30 ? ago.day(days) : date(iso);
    },
  };
  cache.set(locale, f);
  return f;
}

const vi = formatters("vi");
export const fmtDateTime = vi.dateTime;
export const fmtDate = vi.date;
export const fmtNumber = vi.number;
export const fmtVnd = vi.vnd;
export const fmtVndCompact = vi.vndCompact;
export const fmtUsd = vi.usd;
export const fmtPct = vi.pct;
export const fmtScore = vi.score;
export const fmtAgo = vi.ago;

/** Số chữ cái đầu của họ tên, dùng cho avatar (chỉ lấy chữ cái: "reviewer (northwind)" → "RN"). */
export function initials(name: string): string {
  const words = name.match(/\p{L}[\p{L}\p{M}]*/gu) ?? [];
  return ((words[0]?.[0] ?? "") + (words.length > 1 ? (words.at(-1)?.[0] ?? "") : "")).toUpperCase() || "?";
}
