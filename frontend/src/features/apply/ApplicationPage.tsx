"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import type { ApplicationView, Track } from "@/lib/contracts";
import { useGet } from "@/lib/hooks";
import { StatusPanel } from "./StatusPanel";
import { Wizard } from "./Wizard";

export function ApplicationPage({ id }: { id: string }) {
  const client = useQueryClient();
  const view = useGet<ApplicationView>(`/applications/${id}`);
  const tracks = useGet<Track[]>("/tracks", { staleTime: 5 * 60_000 });
  const [editing, setEditing] = useState(false);

  const refresh = async () => {
    setEditing(false);
    await client.invalidateQueries({ predicate: (q) => typeof q.queryKey[1] === "string" && q.queryKey[1].startsWith("/applications") });
  };

  return (
    <div className="stack">
      <p>
        <Link href="/apply">← Hồ sơ của tôi</Link>
      </p>
      <QueryState query={view} lines={6}>
        {(app) => {
          const editable = app.status === "DRAFT" || (app.status === "NEEDS_INFO" && editing);
          return (
            <>
              <PageHeader title={app.intake.name} subtitle={editable ? "Điền thông tin của bạn; bản nháp tự động lưu." : "Theo dõi tiến trình xét tuyển của bạn."} />
              {editable ? (
                <Wizard key={app.version} view={app} tracks={tracks.data ?? []} infoOnly={app.status === "NEEDS_INFO"} onSubmitted={() => void refresh()} />
              ) : (
                <StatusPanel view={app} onEdit={() => setEditing(true)} onChanged={() => void refresh()} />
              )}
            </>
          );
        }}
      </QueryState>
    </div>
  );
}
