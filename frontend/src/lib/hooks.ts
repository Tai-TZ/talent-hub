"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";

/** Đọc dữ liệu; truyền `null` để tạm tắt (ví dụ khi chưa chọn đợt tuyển). */
export function useGet<T>(path: string | null, options: { refetchInterval?: number | false; staleTime?: number } = {}) {
  return useQuery<T, ApiError>({
    queryKey: ["api", path],
    queryFn: () => api<T>(path as string),
    enabled: path !== null,
    refetchInterval: options.refetchInterval,
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
export function errorText(error: unknown, fallback = "Đã có lỗi xảy ra. Vui lòng thử lại."): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "Bạn không có quyền thực hiện thao tác này.";
    if (error.status === 429) return "Thao tác quá nhanh, vui lòng thử lại sau ít phút.";
    if (error.status >= 500) return `${fallback}${error.requestId ? ` (mã ${error.requestId.slice(0, 8)})` : ""}`;
    return error.message || fallback;
  }
  return fallback;
}
