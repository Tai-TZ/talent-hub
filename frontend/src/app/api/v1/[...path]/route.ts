import type { NextRequest } from "next/server";
import { backendFetch, buildBackendHeaders } from "@/lib/backend";
import { MAX_BODY_BYTES, MAX_UPLOAD_BODY_BYTES } from "@/lib/config";

/**
 * BFF: trình duyệt chỉ nói chuyện với Next.js (cùng origin, không cần CORS), Next chuyển tiếp sang backend.
 * Cookie phiên là httpOnly nên JavaScript phía client không đọc được token.
 */
export const dynamic = "force-dynamic";

// location: chuyển hướng OIDC do chính backend tạo (đường dẫn nội bộ hoặc URL xác thực của nhà cung cấp).
const PASS_THROUGH_RESPONSE_HEADERS = ["content-type", "content-disposition", "retry-after", "x-request-id", "location"];

function problem(status: number, title: string): Response {
  return Response.json({ type: "about:blank", title, status, detail: title }, {
    status,
    headers: { "content-type": "application/problem+json", "cache-control": "no-store" },
  });
}

/** Chỉ endpoint tải tài liệu được phép nhận thân yêu cầu lớn. */
function bodyLimit(request: NextRequest, path: string[]): number {
  return request.method === "POST" && path.join("/") === "admin/documents" ? MAX_UPLOAD_BODY_BYTES : MAX_BODY_BYTES;
}

class BodyTooLargeError extends Error {}

/** Đọc thân yêu cầu và dừng ngay khi vượt giới hạn, không phụ thuộc header content-length (có thể thiếu hoặc bị giả). */
async function readBounded(request: NextRequest, limit: number): Promise<ArrayBuffer> {
  if (!request.body) return new ArrayBuffer(0);
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    received += value.byteLength;
    if (received > limit) {
      await reader.cancel();
      throw new BodyTooLargeError();
    }
    chunks.push(value);
  }
  const out = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return out.buffer;
}

async function forward(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await params;
  const hasBody = !["GET", "HEAD"].includes(request.method);

  const limit = bodyLimit(request, path);
  const length = Number(request.headers.get("content-length") ?? "0");
  if (hasBody && length > limit) return problem(413, "Nội dung yêu cầu quá lớn");

  let body: ArrayBuffer | undefined;
  if (hasBody) {
    try {
      body = await readBounded(request, limit);
    } catch (error) {
      if (error instanceof BodyTooLargeError) return problem(413, "Nội dung yêu cầu quá lớn");
      return problem(400, "Không đọc được nội dung yêu cầu");
    }
  }

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
      body,
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
