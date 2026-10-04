import { cookies, headers } from "next/headers";
import { cache } from "react";
import { backendFetch, buildBackendHeaders } from "./backend";
import { DEFAULT_LOCALE, getMessages, isLocale, LOCALE_COOKIE, type Locale, type Messages } from "./i18n";
import type { Me, OrgInfo } from "./types";

async function requestContext() {
  const h = await headers();
  const c = await cookies();
  return {
    host: h.get("host"),
    cookie: c.toString(),
    clientIp: h.get("x-forwarded-for"),
    requestId: h.get("x-request-id"),
  };
}

export type Session = { status: "ok"; me: Me } | { status: "unauthenticated" };

/** Gọi /me ở phía server. 401 nghĩa là chưa đăng nhập hoặc access token đã hết hạn. */
export const getSession = cache(async (): Promise<Session> => {
  const ctx = await requestContext();
  const res = await backendFetch("/api/v1/me", { headers: buildBackendHeaders(ctx) });
  if (res.status === 401) return { status: "unauthenticated" };
  if (!res.ok) throw new Error(`Backend /me trả về ${res.status}`);
  return { status: "ok", me: (await res.json()) as Me };
});

export const getOrgInfo = cache(async (): Promise<OrgInfo | null> => {
  const ctx = await requestContext();
  const res = await backendFetch("/api/v1/org", { headers: buildBackendHeaders({ ...ctx, cookie: null }) });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Backend /org trả về ${res.status}`);
  return (await res.json()) as OrgInfo;
});

export async function getLocale(orgDefault?: string): Promise<Locale> {
  const stored = (await cookies()).get(LOCALE_COOKIE)?.value;
  if (isLocale(stored)) return stored;
  return isLocale(orgDefault) ? orgDefault : DEFAULT_LOCALE;
}

export async function getPathname(): Promise<string> {
  return (await headers()).get("x-pathname") ?? "/dashboard";
}

/** Thông điệp giao diện cho server component. */
export async function getT(): Promise<{ locale: Locale; t: Messages }> {
  const locale = await getLocale();
  return { locale, t: getMessages(locale) };
}
