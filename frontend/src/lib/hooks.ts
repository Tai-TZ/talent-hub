"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { Locale } from "./i18n";

/** Đọc dữ liệu; truyền `null` để tạm tắt (ví dụ khi chưa chọn đợt tuyển). */
export function useGet<T>(
  path: string | null,
  options: { refetchInterval?: number | false | ((data: T | undefined) => number | false); staleTime?: number } = {},
) {
  const interval = options.refetchInterval;
  return useQuery<T, ApiError>({
    queryKey: ["api", path],
    queryFn: () => api<T>(path as string),
    enabled: path !== null,
    refetchInterval: typeof interval === "function" ? (query) => interval(query.state.data) : interval,
    staleTime: options.staleTime,
  });
}

type Method = "POST" | "PUT" | "PATCH" | "DELETE";

/**
 * Gửi thay đổi; thành công thì làm mới mọi truy vấn có đường dẫn bắt đầu bằng một trong các tiền tố `invalidate`.
 * Lỗi nghiệp vụ (409 xung đột phiên bản, 422 theo trường...) được ném ra để màn hình hiển thị.
 */
export function useSend<TOut = unknown, TIn = void>(
  method: Method,
  path: string | ((input: TIn) => string),
  options: { invalidate?: string[] } = {},
) {
  const client = useQueryClient();
  return useMutation<TOut, ApiError, TIn>({
    mutationFn: (input) => api<TOut>(typeof path === "function" ? path(input) : path, { method, json: input === undefined ? undefined : input }),
    onSuccess: async () => {
      const prefixes = options.invalidate ?? [];
      if (prefixes.length === 0) return;
      await client.invalidateQueries({
        predicate: (q) => {
          const key = q.queryKey[1];
          return typeof key === "string" && prefixes.some((p) => key.startsWith(p));
        },
      });
    },
  });
}

/** Thông điệp hiển thị cho người dùng từ một lỗi bất kỳ. */
const ERRORS = {
  vi: {
    generic: "Đã có lỗi xảy ra. Vui lòng thử lại.",
    forbidden: "Bạn không có quyền thực hiện thao tác này.",
    rateLimited: "Thao tác quá nhanh, vui lòng thử lại sau ít phút.",
    code: (id: string) => ` (mã ${id})`,
  },
  en: {
    generic: "Something went wrong. Please try again.",
    forbidden: "You don't have permission to do this.",
    rateLimited: "Too many requests. Please try again in a few minutes.",
    code: (id: string) => ` (ref ${id})`,
  },
} satisfies Record<Locale, unknown>;

/** Thông điệp lỗi nghiệp vụ (4xx) do backend trả về đã theo ngôn ngữ người dùng (BFF gửi Accept-Language). */
export function errorText(error: unknown, fallback?: string, locale: Locale = "vi"): string {
  const m = ERRORS[locale];
  const base = fallback ?? m.generic;
  if (error instanceof ApiError) {
    if (error.status === 403) return m.forbidden;
    if (error.status === 429) return m.rateLimited;
    if (error.status >= 500) return `${base}${error.requestId ? m.code(error.requestId.slice(0, 8)) : ""}`;
    return error.message || base;
  }
  return base;
}
