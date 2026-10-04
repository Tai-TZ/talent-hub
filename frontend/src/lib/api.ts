import type { Problem } from "./types";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly requestId?: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let refreshing: Promise<boolean> | null = null;

/** Làm mới phiên; nhiều request cùng gặp 401 sẽ dùng chung một lần refresh. */
export function refreshSession(): Promise<boolean> {
  refreshing ??= fetch("/api/v1/auth/refresh", { method: "POST", credentials: "same-origin" })
    .then((res) => res.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

async function toError(res: Response): Promise<ApiError> {
  let detail = "";
  let requestId: string | null | undefined;
  try {
    const body = (await res.json()) as Problem;
    detail = body.detail ?? body.title ?? "";
    requestId = body.request_id;
  } catch {
    // Phản hồi không phải JSON: giữ thông điệp rỗng, giao diện sẽ dùng thông điệp chung.
  }
  return new ApiError(res.status, detail, requestId ?? res.headers.get("x-request-id"));
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const build = (): RequestInit => ({
    credentials: "same-origin",
    ...rest,
    headers: { accept: "application/json", ...(json !== undefined ? { "content-type": "application/json" } : {}), ...headers },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });

  let res = await fetch(`/api/v1${path}`, build());
  if (res.status === 401 && !path.startsWith("/auth/") && (await refreshSession())) {
    res = await fetch(`/api/v1${path}`, build());
  }
  if (!res.ok) throw await toError(res);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}
