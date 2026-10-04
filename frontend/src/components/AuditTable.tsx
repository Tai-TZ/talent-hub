"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { AuditPage } from "@/lib/types";
import { useI18n } from "./providers";
import { Alert } from "./ui/Alert";
import { Button } from "./ui/Button";
import { EmptyState } from "./ui/EmptyState";
import { Skeleton } from "./ui/Skeleton";
import { TextField } from "./ui/TextField";

const PAGE_SIZE = 25;

export function AuditTable() {
  const { t, locale } = useI18n();
  const [filter, setFilter] = useState("");
  const [applied, setApplied] = useState("");

  const query = useInfiniteQuery({
    queryKey: ["audit-logs", applied],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
      if (applied) params.set("action", applied);
      if (pageParam) params.set("cursor", pageParam);
      return api<AuditPage>(`/audit-logs?${params}`);
    },
    getNextPageParam: (last) => last.next_cursor,
  });

  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  const formatter = new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-GB", { dateStyle: "short", timeStyle: "medium" });
  const errorMessage = query.error
    ? query.error instanceof ApiError && query.error.status === 403
      ? t.audit.forbidden
      : t.common.genericError
    : null;

  return (
    <div className="stack">
      <form
        className="toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied(filter.trim());
        }}
      >
        <TextField label={t.audit.filter} value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={t.audit.filterPlaceholder} />
        <Button type="submit" variant="secondary">
          {t.audit.filter}
        </Button>
      </form>

      {errorMessage ? (
        <Alert tone="danger">
          {errorMessage}{" "}
          <Button variant="tertiary" size="sm" onClick={() => void query.refetch()}>
            {t.common.retry}
          </Button>
        </Alert>
      ) : null}

      {query.isPending ? (
        <Skeleton lines={5} />
      ) : items.length === 0 && !errorMessage ? (
        <EmptyState title={t.audit.empty} />
      ) : (
        <div className="table-wrap">
          <table className="th-table responsive-table">
            <thead>
              <tr>
                <th scope="col">{t.audit.time}</th>
                <th scope="col">{t.audit.action}</th>
                <th scope="col">{t.audit.entity}</th>
                <th scope="col">{t.audit.request}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td data-label={t.audit.time}>{formatter.format(new Date(item.at))}</td>
                  <td data-label={t.audit.action}>
                    <code>{item.action}</code>
                  </td>
                  <td data-label={t.audit.entity}>{item.entity_type}</td>
                  <td data-label={t.audit.request} className="mono">
                    {item.request_id ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {query.hasNextPage ? (
            <div className="table-footer">
              <Button variant="secondary" loading={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
                {t.common.loadMore}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
