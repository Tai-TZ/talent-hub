/** Định dạng hiển thị theo chuẩn Việt Nam. Các hàm thuần, không phụ thuộc trạng thái. */

const dateTime = new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" });
const dateOnly = new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium" });
const number = new Intl.NumberFormat("vi-VN");
const vnd = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND", maximumFractionDigits: 0 });
const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

export const fmtDateTime = (iso?: string | null) => (iso ? dateTime.format(new Date(iso)) : "—");
export const fmtDate = (iso?: string | null) => (iso ? dateOnly.format(new Date(iso)) : "—");
export const fmtNumber = (n?: number | null) => (n == null ? "—" : number.format(n));
export const fmtVnd = (n?: number | null) => (n == null ? "—" : vnd.format(n));
export const fmtUsd = (n?: number | null) => (n == null ? "—" : usd.format(n));

export function fmtPct(ratio?: number | null, digits = 0): string {
  return ratio == null ? "—" : `${(ratio * 100).toFixed(digits)}%`;
}

export function fmtScore(score?: number | null): string {
  return score == null ? "—" : score.toFixed(1);
}

/** Số chữ cái đầu của họ tên, dùng cho avatar. */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")).toUpperCase();
}

/** Thời gian tương đối ngắn gọn ("3 phút trước") cho thông báo và hoạt động gần đây. */
export function fmtAgo(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "vừa xong";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  const days = Math.floor(hours / 24);
  return days < 30 ? `${days} ngày trước` : fmtDate(iso);
}
