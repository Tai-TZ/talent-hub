"use client";

import { useState } from "react";
import { useMe } from "@/components/providers";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { SelectField, TextArea } from "@/components/ui/Fields";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { QualificationRow } from "@/lib/contracts";
import { errorText, useGet, useSend } from "@/lib/hooks";
import { enrollmentStatus, suggestionLabel } from "@/lib/labels";

function DecideForm({ row, onClose }: { row: QualificationRow; onClose: () => void }) {
  const [outcome, setOutcome] = useState(row.suggestion === "not_qualified" ? "not_qualified" : "qualified");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const decide = useSend<unknown, { outcome: string; reason: string }>("POST", `/enrollments/${row.enrollment_id}/qualification`, { invalidate: ["/cohorts"] });
  const against = (row.suggestion === "qualified" && outcome === "not_qualified") || (row.suggestion === "not_qualified" && outcome === "qualified");
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        decide.mutate({ outcome, reason }, { onSuccess: onClose, onError: (err) => setError(errorText(err)) });
      }}
    >
      <p>
        <strong>{row.name}</strong> · đạt {row.met}/{row.total} năng lực mục tiêu · <StatusBadge entry={suggestionLabel(row.suggestion)} />
      </p>
      <SelectField label="Kết quả" value={outcome} onChange={(e) => setOutcome(e.target.value)} help="Hệ thống chỉ gợi ý theo năng lực; người quản lý quyết định.">
        <option value="qualified">Đạt yêu cầu</option>
        <option value="not_qualified">Chưa đạt yêu cầu</option>
      </SelectField>
      {against ? <Alert tone="warning">Kết quả khác với gợi ý theo dữ liệu đánh giá. Hãy ghi rõ lý do; việc này được lưu trong nhật ký.</Alert> : null}
      <TextArea label="Lý do" required rows={3} value={reason} maxLength={2000} onChange={(e) => setReason(e.target.value)} help="Tối thiểu 10 ký tự." />
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="dialog__actions">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button type="submit" loading={decide.isPending} disabled={reason.trim().length < 10}>
          Chốt kết quả
        </Button>
      </div>
    </form>
  );
}

export function QualificationTab({ cohortId }: { cohortId: string }) {
  const me = useMe();
  const canManage = me.permissions.includes("cohort.manage");
  const query = useGet<QualificationRow[]>(`/cohorts/${cohortId}/qualification`);
  const [active, setActive] = useState<QualificationRow | null>(null);

  return (
    <div className="stack">
      <p className="muted">
        Gợi ý đạt/chưa đạt được tính từ mức năng lực mới nhất do mentor đánh giá so với chuẩn của nhánh. Quyết định cuối cùng thuộc về người quản lý và luôn kèm lý do.
      </p>
      <QueryState query={query} lines={5}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState title="Chưa có học viên trong khoá" />
          ) : (
            <div className="table-wrap">
              <table className="th-table responsive-table">
                <thead>
                  <tr>
                    <th scope="col">Học viên</th>
                    <th scope="col">Nhánh</th>
                    <th scope="col">Năng lực đạt chuẩn</th>
                    <th scope="col">Gợi ý</th>
                    <th scope="col">Trạng thái</th>
                    {canManage ? <th scope="col">Thao tác</th> : null}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.enrollment_id}>
                      <td data-label="Học viên">
                        {r.name}
                        <div className="muted mono">{r.candidate_code}</div>
                      </td>
                      <td data-label="Nhánh">{r.track_name ?? "—"}</td>
                      <td data-label="Năng lực">{r.total > 0 ? `${r.met}/${r.total}` : "—"}</td>
                      <td data-label="Gợi ý">
                        <StatusBadge entry={suggestionLabel(r.suggestion)} />
                      </td>
                      <td data-label="Trạng thái">
                        <StatusBadge entry={enrollmentStatus(r.status)} />
                      </td>
                      {canManage ? (
                        <td data-label="Thao tác">
                          {r.status === "active" && r.track_name ? (
                            <Button variant="tertiary" size="sm" onClick={() => setActive(r)}>
                              Xét kết quả
                            </Button>
                          ) : null}
                        </td>
                      ) : null}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </QueryState>
      <Dialog open={active !== null} title="Xét kết quả khoá học" size="sm" onClose={() => setActive(null)}>
        {active ? <DecideForm row={active} onClose={() => setActive(null)} /> : null}
      </Dialog>
    </div>
  );
}
