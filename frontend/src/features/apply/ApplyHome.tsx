"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button, ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { ApplicationSummary, IntakeT } from "@/lib/contracts";
import { fmtDate } from "@/lib/format";
import { errorText, useGet, useSend } from "@/lib/hooks";
import { applicationStatus } from "@/lib/labels";

function IntakeCard({ intake, existing }: { intake: IntakeT; existing?: ApplicationSummary }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const create = useSend<{ id: string }, { intake_id: string }>("POST", "/applications", { invalidate: ["/applications"] });
  const start = () => {
    setError(null);
    create.mutate({ intake_id: intake.id }, { onSuccess: (app) => router.push(`/apply/${app.id}`), onError: (e) => setError(errorText(e)) });
  };

  return (
    <article className="th-card link-card stack">
      <h3 className="link-card__title">{intake.name}</h3>
      <p className="muted clamp-3">{intake.description}</p>
      <p className="muted">
        Hạn nộp: <strong>{fmtDate(intake.closes_at)}</strong> · {intake.quota} suất · {intake.rounds.length} vòng xét
      </p>
      {error ? <Alert tone="danger">{error}</Alert> : null}
      {existing ? (
        <ButtonLink href={`/apply/${existing.id}`} variant="secondary">
          {existing.status === "DRAFT" ? "Tiếp tục điền hồ sơ" : "Xem hồ sơ"}
        </ButtonLink>
      ) : (
        <Button onClick={start} loading={create.isPending}>
          Bắt đầu ứng tuyển
        </Button>
      )}
    </article>
  );
}

export function ApplyHome() {
  const mine = useGet<ApplicationSummary[]>("/applications/mine");
  const intakes = useGet<IntakeT[]>("/intakes");

  return (
    <div className="stack">
      <PageHeader title="Hồ sơ của tôi" subtitle="Nộp hồ sơ, theo dõi từng vòng xét tuyển và nhận thông báo kết quả." />

      <section className="stack" aria-labelledby="mine-title">
        <h2 id="mine-title" className="th-type-h4">
          Hồ sơ đã tạo
        </h2>
        <QueryState query={mine} lines={2}>
          {(items) =>
            items.length === 0 ? (
              <EmptyState title="Bạn chưa có hồ sơ nào">Chọn một đợt tuyển bên dưới để bắt đầu.</EmptyState>
            ) : (
              <ul className="card-grid plain-list">
                {items.map((a) => (
                  <li key={a.id}>
                    <Link href={`/apply/${a.id}`} className="th-card th-card--interactive link-card">
                      <span className="link-card__title">{a.intake.name}</span>
                      <span>
                        <StatusBadge entry={applicationStatus(a.status)} />
                      </span>
                      <span className="link-card__desc">
                        Mã <span className="mono">{a.candidate_code}</span>
                        {a.submitted_at ? ` · nộp ${fmtDate(a.submitted_at)}` : " · chưa nộp"}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )
          }
        </QueryState>
      </section>

      <section className="stack" aria-labelledby="open-title">
        <h2 id="open-title" className="th-type-h4">
          Đợt tuyển đang mở
        </h2>
        <QueryState query={intakes} lines={3}>
          {(list) =>
            list.length === 0 ? (
              <EmptyState title="Hiện chưa có đợt tuyển nào đang mở" />
            ) : (
              <div className="card-grid">
                {list.map((i) => (
                  <IntakeCard key={i.id} intake={i} existing={mine.data?.find((a) => a.intake.id === i.id)} />
                ))}
              </div>
            )
          }
        </QueryState>
      </section>
    </div>
  );
}
