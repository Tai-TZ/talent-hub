"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { ApprovalRow } from "@/lib/contracts";
import { fmtNumber, fmtScore } from "@/lib/format";
import { useGet } from "@/lib/hooks";
import { outcomeLabel, tierLabel } from "@/lib/labels";
import { ApproveDialog, ReturnDialog } from "./DecisionDialogs";

type Active = { row: ApprovalRow; kind: "approve" | "return" } | null;

export function ApprovalsView() {
  const query = useGet<ApprovalRow[]>("/staff/approvals");
  const [active, setActive] = useState<Active>(null);
  const close = () => setActive(null);
  const done = () => {
    close();
    void query.refetch();
  };

  return (
    <div className="stack">
      <PageHeader title="Phê duyệt quyết định" subtitle="Quyết định cuối cùng do người phê duyệt đưa ra, độc lập với người đề xuất (bốn mắt)." />
      <QueryState query={query} lines={5}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState title="Không có đề xuất nào đang chờ">Khi người chấm đề xuất quyết định, hồ sơ sẽ xuất hiện ở đây.</EmptyState>
          ) : (
            <>
              <p className="muted" aria-live="polite">
                {fmtNumber(rows.length)} đề xuất đang chờ
              </p>
              <div className="table-wrap">
                <table className="th-table responsive-table">
                  <thead>
                    <tr>
                      <th scope="col">Hồ sơ</th>
                      <th scope="col">Đợt tuyển</th>
                      <th scope="col">Đề xuất</th>
                      <th scope="col">Lý do</th>
                      <th scope="col">Điểm TB</th>
                      <th scope="col">Gợi ý AI</th>
                      <th scope="col">Thao tác</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.decision_id}>
                        <td data-label="Hồ sơ">
                          <Link href={`/staff/applications/${row.application_id}`} className="mono">
                            {row.candidate_code}
                          </Link>
                          <div className="muted">{row.name ?? "Ẩn danh"}</div>
                        </td>
                        <td data-label="Đợt tuyển">{String(row.intake["name"] ?? "")}</td>
                        <td data-label="Đề xuất">
                          <StatusBadge entry={outcomeLabel(row.proposed_outcome)} />
                        </td>
                        <td data-label="Lý do">
                          <span className="clamp-2">{row.proposal_reason}</span>
                        </td>
                        <td data-label="Điểm TB">
                          {fmtScore(row.avg_score)} <span className="muted">({row.review_count} lượt)</span>
                        </td>
                        <td data-label="Gợi ý AI">
                          {row.ai_tier ? (
                            <span className="row-actions">
                              <StatusBadge entry={tierLabel(row.ai_tier)} />
                              <span className="score-chip">{fmtScore(row.ai_score)}</span>
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td data-label="Thao tác">
                          {row.proposed_by_me ? (
                            <span className="muted">Bạn đề xuất, cần người khác duyệt</span>
                          ) : (
                            <span className="row-actions">
                              <Button size="sm" onClick={() => setActive({ row, kind: "approve" })}>
                                Duyệt
                              </Button>
                              <Button size="sm" variant="secondary" onClick={() => setActive({ row, kind: "return" })}>
                                Trả lại
                              </Button>
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )
        }
      </QueryState>

      {active ? (
        <>
          <ApproveDialog decisionId={active.row.decision_id} proposedOutcome={active.row.proposed_outcome} version={active.row.version} open={active.kind === "approve"} onClose={close} onDone={done} />
          <ReturnDialog decisionId={active.row.decision_id} version={active.row.version} open={active.kind === "return"} onClose={close} onDone={done} />
        </>
      ) : null}
    </div>
  );
}
