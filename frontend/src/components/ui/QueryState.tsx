"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { errorText } from "@/lib/hooks";
import { Alert } from "./Alert";
import { Button } from "./Button";
import { Skeleton } from "./Skeleton";

/** Bọc truy vấn: khung chờ khi đang tải, thông báo lỗi có nút thử lại, rồi mới hiển thị nội dung. */
export function QueryState<T>({
  query,
  lines = 4,
  children,
}: {
  query: UseQueryResult<T, Error>;
  lines?: number;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <Skeleton lines={lines} />;
  if (query.isError) {
    return (
      <Alert tone="danger">
        {errorText(query.error)}{" "}
        <Button variant="tertiary" size="sm" onClick={() => void query.refetch()}>
          Thử lại
        </Button>
      </Alert>
    );
  }
  return <>{children(query.data)}</>;
}
