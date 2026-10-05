import { BACKEND_TIMEOUT_MS, BACKEND_URL, BASE_DOMAIN, DEFAULT_ORG, INTERNAL_PROXY_SECRET } from "./config";
import { resolveOrgSlug } from "./org";

export interface ForwardContext {
  host: string | null;
  cookie?: string | null;
  clientIp?: string | null;
  requestId?: string | null;
  contentType?: string | null;
  origin?: string | null;
  accept?: string | null;
  /** Chỉ chuyển cho /api/v1/integrations/* (khoá tích hợp của Power BI, LMS, CRM). */
  authorization?: string | null;
}

/** Header gửi sang backend. Tổ chức luôn được tính lại từ Host, không bao giờ tin giá trị client gửi. */
export function buildBackendHeaders(ctx: ForwardContext): Headers {
  const headers = new Headers();
  headers.set("x-organization", resolveOrgSlug(ctx.host, BASE_DOMAIN, DEFAULT_ORG));
  if (INTERNAL_PROXY_SECRET) headers.set("x-internal-auth", INTERNAL_PROXY_SECRET);
  if (ctx.cookie) headers.set("cookie", ctx.cookie);
  if (ctx.clientIp) headers.set("x-forwarded-for", ctx.clientIp);
  if (ctx.requestId) headers.set("x-request-id", ctx.requestId);
  if (ctx.contentType) headers.set("content-type", ctx.contentType);
  if (ctx.origin) headers.set("origin", ctx.origin);
  if (ctx.authorization) headers.set("authorization", ctx.authorization);
  headers.set("accept", ctx.accept ?? "application/json");
  // Ngôn ngữ giao diện (cookie `locale`) để backend trả thông điệp lỗi đúng ngôn ngữ người dùng đang xem.
  headers.set("accept-language", localeFromCookie(ctx.cookie));
  return headers;
}

function localeFromCookie(cookie: string | null | undefined): string {
  const match = /(?:^|;\s*)locale=([a-z]{2})(?:;|$)/.exec(cookie ?? "");
  return match?.[1] === "en" ? "en" : "vi";
}

export function backendFetch(path: string, init: RequestInit & { headers: Headers }): Promise<Response> {
  return fetch(`${BACKEND_URL}${path}`, {
    ...init,
    cache: "no-store",
    redirect: "manual",
    signal: AbortSignal.timeout(BACKEND_TIMEOUT_MS),
  });
}
