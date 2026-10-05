"use client";

import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { QueryState } from "@/components/ui/QueryState";
import type { NotificationList } from "@/lib/contracts";
import { fmtAgo } from "@/lib/format";
import { useGet, useSend } from "@/lib/hooks";

export function Notifications() {
  const query = useGet<NotificationList>("/notifications?limit=8", { refetchInterval: 60_000 });
  const mark = useSend<unknown, { id?: string }>("POST", "/notifications/read", { invalidate: ["/notifications"] });

  return (
    <section aria-labelledby="notif-title" className="stack">
      <div className="row-actions">
        <h2 id="notif-title" className="th-type-h4">
          Thông báo
        </h2>
        {query.data && query.data.unread > 0 ? (
          <Button variant="tertiary" size="sm" loading={mark.isPending} onClick={() => mark.mutate({})}>
            Đánh dấu đã đọc tất cả ({query.data.unread})
          </Button>
        ) : null}
      </div>
      <QueryState query={query} lines={2}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState title="Chưa có thông báo nào" />
          ) : (
            <ul className="plain-list notif-list">
              {data.items.map((n) => (
                <li key={n.id} className={`notif ${n.read ? "" : "notif--unread"}`}>
                  <div className="notif__head">
                    {n.link ? (
                      <Link href={n.link} onClick={() => !n.read && mark.mutate({ id: n.id })}>
                        {n.title}
                      </Link>
                    ) : (
                      <strong>{n.title}</strong>
                    )}
                    <span className="muted">{fmtAgo(n.created_at)}</span>
                  </div>
                  <p className="muted clamp-2">{n.body}</p>
                </li>
              ))}
            </ul>
          )
        }
      </QueryState>
    </section>
  );
}
