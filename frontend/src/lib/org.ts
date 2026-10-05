const SLUG = /^[a-z0-9][a-z0-9-]{0,62}$/;

/**
 * Xác định tổ chức từ Host: `<slug>.<baseDomain>` → slug; còn lại dùng tổ chức mặc định.
 * Chỉ trả về slug hợp lệ để không đưa giá trị tuỳ ý của client vào header gửi backend.
 */
export function resolveOrgSlug(host: string | null | undefined, baseDomain: string, defaultOrg: string): string {
  const hostname = (host ?? "").split(":")[0]?.toLowerCase() ?? "";
  const suffix = `.${baseDomain.toLowerCase()}`;
  if (hostname.endsWith(suffix)) {
    const label = hostname.slice(0, -suffix.length);
    if (label && !label.includes(".") && SLUG.test(label)) return label;
  }
  return defaultOrg;
}

const hasControlChar = (s: string) => [...s].some((c) => c.charCodeAt(0) < 0x20 || c.charCodeAt(0) === 0x7f);
const PROBE = "http://next.invalid";

/**
 * Chỉ cho phép chuyển hướng tới đường dẫn nội bộ (chặn open redirect).
 * Trình phân tích URL bỏ qua tab/xuống dòng nên "/	/evil.com" thành "//evil.com": chặn ký tự điều khiển,
 * rồi lấy chính URL parser làm chuẩn cuối cùng (đường dẫn phải ở lại cùng origin).
 */
export function safeNextPath(next: string | null | undefined, fallback = "/dashboard"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\") || hasControlChar(next)) return fallback;
  try {
    if (new URL(next, PROBE).origin !== PROBE) return fallback;
  } catch {
    return fallback;
  }
  return next;
}
