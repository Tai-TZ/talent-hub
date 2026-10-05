"use client";

import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { TextArea } from "@/components/ui/Fields";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { ApplicationView, TimelineEvent } from "@/lib/contracts";
import { fmtDateTime } from "@/lib/format";
import { errorText, useGet, useSend } from "@/lib/hooks";
import { applicationStatus, eventLabel } from "@/lib/labels";

function RoundProgress({ view }: { view: ApplicationView }) {
  const rounds = view.intake.rounds;
  const currentIndex = rounds.findIndex((r) => r.key === view.current_round);
  const finished = ["ACCEPTED", "REJECTED", "WAITLISTED", "ENROLLED"].includes(view.status);
  return (
    <ol className="round-progress" aria-label="Tiến trình xét tuyển">
      <li className="round-progress__item round-progress__item--done">
        <span className="round-progress__dot" aria-hidden="true" />
        Nộp hồ sơ
      </li>
      {rounds.map((r, i) => {
        const state = finished || (currentIndex >= 0 && i < currentIndex) ? "done" : i === currentIndex ? "current" : "todo";
        return (
          <li key={r.key} className={`round-progress__item round-progress__item--${state}`} aria-current={state === "current" ? "step" : undefined}>
            <span className="round-progress__dot" aria-hidden="true" />
            {r.label}
          </li>
        );
      })}
      <li className={`round-progress__item round-progress__item--${finished ? "done" : "todo"}`}>
        <span className="round-progress__dot" aria-hidden="true" />
        Kết quả
      </li>
    </ol>
  );
}

export function StatusPanel({ view, onEdit, onChanged }: { view: ApplicationView; onEdit: () => void; onChanged: () => void }) {
  const timeline = useGet<TimelineEvent[]>(`/applications/${view.id}/timeline`);
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const [reason, setReason] = useState("");
  const withdraw = useSend<unknown, { reason: string }>("POST", `/applications/${view.id}/withdraw`);
  const resubmit = useSend<unknown, { version: number }>("POST", `/applications/${view.id}/resubmit`);
  const [actionError, setActionError] = useState<string | null>(null);

  const status = applicationStatus(view.status);
  const needsInfo = view.status === "NEEDS_INFO";
  const lastInfoRequest = needsInfo ? timeline.data?.filter((e) => e.type === "info.requested").at(-1) : undefined;
  const canWithdraw = !["WITHDRAWN", "REJECTED", "ENROLLED"].includes(view.status);

  return (
    <div className="stack">
      <section className="th-card form-card stack" aria-labelledby="progress-title">
        <div className="row-actions">
          <h2 id="progress-title" className="th-type-h3">
            Tình trạng hồ sơ
          </h2>
          <StatusBadge entry={status} />
        </div>
        <p className="muted">
          Mã hồ sơ <strong className="mono">{view.candidate_code}</strong> · {view.intake.name}
          {view.submitted_at ? ` · nộp lúc ${fmtDateTime(view.submitted_at)}` : ""}
        </p>
        <RoundProgress view={view} />

        {needsInfo ? (
          <Alert tone="warning" title="Cần bổ sung thông tin">
            {lastInfoRequest?.message ?? "Cán bộ xét tuyển đề nghị bạn bổ sung thông tin."}
            <div className="row-actions" style={{ marginTop: "var(--th-space-3)" }}>
              <Button variant="secondary" size="sm" onClick={onEdit}>
                Chỉnh sửa hồ sơ
              </Button>
              <Button
                size="sm"
                loading={resubmit.isPending}
                onClick={() => {
                  setActionError(null);
                  resubmit.mutate({ version: view.version }, { onSuccess: onChanged, onError: (e) => setActionError(errorText(e)) });
                }}
              >
                Gửi lại hồ sơ
              </Button>
            </div>
          </Alert>
        ) : null}
        {view.status === "ACCEPTED" ? <Alert tone="success">Chúc mừng! Hồ sơ của bạn đã được nhận. Chương trình sẽ liên hệ về bước nhập học.</Alert> : null}
        {view.status === "WAITLISTED" ? <Alert tone="info">Bạn đang trong danh sách dự bị. Chúng tôi sẽ thông báo ngay khi có suất.</Alert> : null}
        {view.status === "REJECTED" ? <Alert tone="info">Rất tiếc hồ sơ lần này chưa phù hợp. Cảm ơn bạn đã quan tâm đến chương trình.</Alert> : null}
        {actionError ? <Alert tone="danger">{actionError}</Alert> : null}

        {canWithdraw ? (
          <div>
            <Button variant="tertiary" size="sm" onClick={() => setWithdrawOpen(true)}>
              Rút hồ sơ
            </Button>
          </div>
        ) : null}
      </section>

      <section className="th-card form-card stack" aria-labelledby="timeline-title">
        <h2 id="timeline-title" className="th-type-h4">
          Lịch sử xử lý
        </h2>
        <QueryState query={timeline} lines={3}>
          {(events) => (
            <ol className="timeline">
              {[...events].reverse().map((e) => (
                <li key={e.id} className="timeline__item">
                  <div>{eventLabel(e.type)}</div>
                  {e.message ? <div className="muted">{e.message}</div> : null}
                  <div className="timeline__time">{fmtDateTime(e.at)}</div>
                </li>
              ))}
            </ol>
          )}
        </QueryState>
      </section>

      <Dialog
        open={withdrawOpen}
        title="Rút hồ sơ"
        size="sm"
        onClose={() => setWithdrawOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setWithdrawOpen(false)}>
              Giữ hồ sơ
            </Button>
            <Button
              variant="danger"
              loading={withdraw.isPending}
              onClick={() =>
                withdraw.mutate(
                  { reason },
                  {
                    onSuccess: () => {
                      setWithdrawOpen(false);
                      onChanged();
                    },
                    onError: (e) => setActionError(errorText(e)),
                  },
                )
              }
            >
              Xác nhận rút
            </Button>
          </>
        }
      >
        <p>Sau khi rút, hồ sơ sẽ không được xét nữa và bạn không thể hoàn tác.</p>
        <TextArea label="Lý do (không bắt buộc)" rows={3} value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
      </Dialog>
    </div>
  );
}
