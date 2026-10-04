import type { NextRequest } from "next/server";
import { backendFetch, buildBackendHeaders } from "@/lib/backend";
import { MAX_BODY_BYTES } from "@/lib/config";

/**
 * BFF: trình duyệt chỉ nói chuyện với Next.js (cùng origin, không cần CORS), Next chuyển tiếp sang backend.
 * Cookie phiên là httpOnly nên JavaScript phía client không đọc được token.
 */
export const dynamic = "force-dynamic";

const PASS_THROUGH_RESPONSE_HEADERS = ["content-type", "retry-after", "x-request-id"];

function problem(status: number, title: string): Response {
  return Response.json({ type: "about:blank", title, status, detail: title }, {
    status,
    headers: { "content-type": "application/problem+json", "cache-control": "no-store" },
  });
}

async function forward(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await params;
  const hasBody = !["GET", "HEAD"].includes(request.method);

  const length = Number(request.headers.get("content-length") ?? "0");
  if (hasBody && length > MAX_BODY_BYTES) return problem(413, "Nội dung yêu cầu quá lớn");

  const forwardedFor = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? null;
  const headers = buildBackendHeaders({
    host: request.headers.get("host"),
    cookie: request.headers.get("cookie"),
    clientIp: forwardedFor,
    requestId: request.headers.get("x-request-id"),
    contentType: request.headers.get("content-type"),
    origin: request.headers.get("origin"),
    accept: request.headers.get("accept"),
  });

  let upstream: Response;
  try {
    upstream = await backendFetch(`/api/v1/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
    });
  } catch {
    return problem(502, "Không kết nối được máy chủ");
  }

  const out = new Headers({ "cache-control": "no-store" });
  for (const name of PASS_THROUGH_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  for (const cookie of upstream.headers.getSetCookie()) out.append("set-cookie", cookie);
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
