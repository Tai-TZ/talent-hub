"use client";

import { useState } from "react";
import { useMe } from "@/components/providers";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { TextField } from "@/components/ui/TextField";
import type { StipendSummary } from "@/lib/contracts";
import { fmtNumber, fmtVnd } from "@/lib/format";
import { errorText, useGet, useSend } from "@/lib/hooks";

const thisMonth = () => new Date().toISOString().slice(0, 7);

export function StipendsTab({ cohortId }: { cohortId: string }) {
  const me = useMe();
  const canManage = me.permissions.includes("cohort.manage");
  const query = useGet<StipendSummary[]>(`/cohorts/${cohortId}/stipends`);
  const [period, setPeriod] = useState(thisMonth());
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const generate = useSend<{ created: number }, { period: string }>("POST", `/cohorts/${cohortId}/stipends/generate`, { invalidate: [`/cohorts/${cohortId}/stipends`] });
  const pay = useSend<{ count: number; total_vnd: number }, { period: string }>("POST", `/cohorts/${cohortId}/stipends/pay`, { invalidate: [`/cohorts/${cohortId}/stipends`, "/admin/costs"] });

  return (
    <div className="stack">
      <Alert tone="info" title="Chỉ ghi nhận, không chuyển tiền">
        Hệ thống tính danh sách học viên đủ điều kiện nhận phụ cấp từng kỳ và ghi bút toán chi phí khi bạn đánh dấu đã chi. Việc chuyển khoản thực hiện ở hệ thống kế toán của trường.
      </Alert>

      {canManage ? (
        <form
          className="toolbar"
          onSubmit={(e) => {
            e.preventDefault();
            setMessage(null);
            generate.mutate(
              { period },
              {
                onSuccess: (r) => setMessage({ tone: "success", text: r.created > 0 ? `Đã tạo ${fmtNumber(r.created)} khoản phụ cấp kỳ ${period}.` : `Kỳ ${period} đã đủ khoản cho mọi học viên đang học.` }),
                onError: (err) => setMessage({ tone: "danger", text: errorText(err) }),
              },
            );
          }}
        >
          <TextField label="Kỳ phụ cấp" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} required />
          <Button type="submit" variant="secondary" loading={generate.isPending}>
            Tạo khoản phụ cấp cho kỳ này
          </Button>
        </form>
      ) : null}
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}

      <QueryState query={query} lines={3}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState title="Chưa có kỳ phụ cấp nào" />
          ) : (
            <div className="table-wrap">
              <table className="th-table responsive-table">
                <thead>
                  <tr>
                    <th scope="col">Kỳ</th>
                    <th scope="col">Trạng thái</th>
                    <th scope="col">Số học viên</th>
                    <th scope="col">Tổng tiền</th>
                    {canManage ? <th scope="col">Thao tác</th> : null}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={`${r.period}-${r.status}`}>
                      <td data-label="Kỳ">{r.period}</td>
                      <td data-label="Trạng thái">
                        <StatusBadge entry={r.status === "paid" ? ["Đã chi", "success"] : ["Đủ điều kiện", "warning"]} />
                      </td>
                      <td data-label="Số học viên">{fmtNumber(r.count)}</td>
                      <td data-label="Tổng tiền">{fmtVnd(r.total_vnd)}</td>
                      {canManage ? (
                        <td data-label="Thao tác">
                          {r.status === "eligible" ? (
                            <Button
                              size="sm"
                              variant="secondary"
                              loading={pay.isPending && pay.variables?.period === r.period}
                              onClick={() => {
                                setMessage(null);
                                pay.mutate(
                                  { period: r.period },
                                  {
                                    onSuccess: (res) => setMessage({ tone: "success", text: `Đã ghi nhận chi ${fmtVnd(res.total_vnd)} cho ${fmtNumber(res.count)} học viên (kỳ ${r.period}) vào sổ chi phí.` }),
                                    onError: (err) => setMessage({ tone: "danger", text: errorText(err) }),
                                  },
                                );
                              }}
                            >
                              Đánh dấu đã chi
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
    </div>
  );
}
