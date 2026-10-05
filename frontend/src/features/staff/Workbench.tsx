"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMe } from "@/components/providers";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { StaffApplication } from "@/lib/contracts";
import { fmtDateTime } from "@/lib/format";
import { errorText, useGet, useSend } from "@/lib/hooks";
import { applicationStatus, eventLabel, outcomeLabel } from "@/lib/labels";
import { AiPanel } from "./AiPanel";
import { CandidateRecord } from "./CandidateRecord";
import { ApproveDialog, ProposeDialog, RequestInfoDialog, ReturnDialog } from "./DecisionDialogs";
import { OtherReviews, ReviewPanel } from "./ReviewPanel";

type Dialogs = "info" | "propose" | "approve" | "return" | null;

function PendingDecision({ app, canApprove, onApprove, onReturn }: { app: StaffApplication; canApprove: boolean; onApprove: () => void; onReturn: () => void }) {
  const d = app.pending_decision;
  if (!d) return null;
  return (
    <section className="th-card panel stack" aria-labelledby="pending-title">
      <h2 id="pending-title" className="th-type-h4">
        Đề xuất đang chờ phê duyệt
      </h2>
      <p>
        Đề xuất: <StatusBadge entry={outcomeLabel(d.proposed_outcome)} />
        {d.proposed_by_me ? <span className="muted"> · do bạn đề xuất</span> : null}
      </p>
      <p className="record-text">{d.proposal_reason}</p>
      {canApprove && d.proposed_by_me ? <Alert tone="info">Bạn là người đề xuất nên không thể tự phê duyệt (nguyên tắc bốn mắt). Cần người phê duyệt khác.</Alert> : null}
      {canApprove && !d.proposed_by_me ? (
        <div className="row-actions">
          <Button onClick={onApprove}>Phê duyệt</Button>
          <Button variant="secondary" onClick={onReturn}>
            Trả lại
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function Body({ app, refresh }: { app: StaffApplication; refresh: () => void }) {
  const me = useMe();
  const [dialog, setDialog] = useState<Dialogs>(null);
  const [active, setActive] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const advance = useSend<unknown, { version: number }>("POST", `/staff/applications/${app.id}/advance`, { invalidate: ["/staff/applications"] });

  const can = (p: string) => me.permissions.includes(p);
  const inRound = app.status === "IN_ROUND";
  const rounds = app.intake.rounds;
  const roundIndex = rounds.findIndex((r) => r.key === app.current_round);
  const isLastRound = roundIndex >= 0 && roundIndex === rounds.length - 1;
  const roundLabel = rounds[roundIndex]?.label;
  const done = () => {
    setDialog(null);
    setActionError(null);
    refresh();
  };

  const highlights = useMemo(() => {
    const out: Record<string, string[]> = {};
    if (!app.ai || app.ai.locked || !active) return out;
    for (const e of app.ai.evidence[active] ?? []) (out[e.field] ??= []).push(e.quote);
    return out;
  }, [app.ai, active]);

  return (
    <div className="stack">
      <p>
        <Link href={`/staff/queue?intake=${app.intake.id}`}>← Hàng đợi hồ sơ</Link>
      </p>
      <PageHeader
        title={`Hồ sơ ${app.candidate_code}`}
        subtitle={
          <>
            {app.profile?.full_name ? <strong>{app.profile.full_name} · </strong> : null}
            {app.intake.name}
            {roundLabel ? ` · vòng ${roundLabel}` : ""}
          </>
        }
        actions={
          <>
            <StatusBadge entry={applicationStatus(app.status)} />
            {inRound && can("application.review") ? (
              <Button variant="secondary" size="sm" onClick={() => setDialog("info")}>
                Yêu cầu bổ sung
              </Button>
            ) : null}
            {inRound && can("application.review") && !isLastRound ? (
              <Button
                variant="secondary"
                size="sm"
                loading={advance.isPending}
                onClick={() => {
                  setActionError(null);
                  advance.mutate({ version: app.version }, { onSuccess: done, onError: (e) => setActionError(errorText(e)) });
                }}
              >
                Chuyển vòng tiếp theo
              </Button>
            ) : null}
            {inRound && can("decision.propose") ? (
              <Button size="sm" onClick={() => setDialog("propose")}>
                Đề xuất quyết định
              </Button>
            ) : null}
          </>
        }
      />
      {actionError ? <Alert tone="danger">{actionError}</Alert> : null}
      {inRound && can("application.review") ? (
        <a className="stacked-only" href="#review">
          Đến phần chấm điểm ↓
        </a>
      ) : null}

      <div className="split split--sidebar">
        <div className="stack">
          <section className="th-card panel" aria-label="Nội dung hồ sơ">
            <CandidateRecord app={app} highlights={highlights} />
          </section>
        </div>

        <aside className="stack" aria-label="Đánh giá">
          <PendingDecision app={app} canApprove={can("decision.approve")} onApprove={() => setDialog("approve")} onReturn={() => setDialog("return")} />
          {app.ai ? <AiPanel ai={app.ai} app={app} criteria={app.rubric?.criteria ?? []} active={active} onActivate={setActive} /> : null}
          {inRound && can("application.review") ? <ReviewPanel app={app} onChanged={refresh} /> : null}
          <OtherReviews app={app} />
          <section className="th-card panel stack" aria-labelledby="history-title">
            <h2 id="history-title" className="th-type-h4">
              Lịch sử xử lý
            </h2>
            <ol className="timeline">
              {[...app.timeline].reverse().map((e, i) => (
                <li key={i} className="timeline__item">
                  <div>{eventLabel(e.type)}</div>
                  {e.message ? <div className="muted">{e.message}</div> : null}
                  <div className="timeline__time">{fmtDateTime(e.at)}</div>
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>

      <RequestInfoDialog applicationId={app.id} version={app.version} open={dialog === "info"} onClose={() => setDialog(null)} onDone={done} />
      <ProposeDialog applicationId={app.id} version={app.version} open={dialog === "propose"} onClose={() => setDialog(null)} onDone={done} />
      {app.pending_decision ? (
        <>
          <ApproveDialog decisionId={app.pending_decision.id} proposedOutcome={app.pending_decision.proposed_outcome} version={app.version} open={dialog === "approve"} onClose={() => setDialog(null)} onDone={done} />
          <ReturnDialog decisionId={app.pending_decision.id} version={app.version} open={dialog === "return"} onClose={() => setDialog(null)} onDone={done} />
        </>
      ) : null}
    </div>
  );
}

export function Workbench({ id }: { id: string }) {
  const query = useGet<StaffApplication>(`/staff/applications/${id}`);
  return (
    <QueryState query={query} lines={8}>
      {(app) => <Body key={`${app.id}:${app.version}:${app.my_review?.submitted ?? false}`} app={app} refresh={() => void query.refetch()} />}
    </QueryState>
  );
}
