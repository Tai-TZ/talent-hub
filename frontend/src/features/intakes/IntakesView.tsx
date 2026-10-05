"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { IntakeT } from "@/lib/contracts";
import { fmtDate, fmtNumber } from "@/lib/format";
import { useGet } from "@/lib/hooks";
import { intakeStatus } from "@/lib/labels";
import { IntakeForm } from "./IntakeForm";

export function IntakesView() {
  const query = useGet<IntakeT[]>("/intakes");
  const [open, setOpen] = useState(false);
  return (
    <div className="stack">
      <PageHeader
        title="Đợt tuyển"
        subtitle="Tạo đợt tuyển, thiết lập rubric từng vòng, mở và đóng nhận hồ sơ."
        actions={<Button onClick={() => setOpen(true)}>Tạo đợt tuyển</Button>}
      />
      <QueryState query={query} lines={4}>
        {(list) =>
          list.length === 0 ? (
            <EmptyState title="Chưa có đợt tuyển nào">Tạo đợt tuyển đầu tiên để bắt đầu nhận hồ sơ.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="th-table responsive-table">
                <thead>
                  <tr>
                    <th scope="col">Đợt tuyển</th>
                    <th scope="col">Trạng thái</th>
                    <th scope="col">Thời gian nhận hồ sơ</th>
                    <th scope="col">Chỉ tiêu</th>
                    <th scope="col">Hồ sơ đã nộp</th>
                    <th scope="col">Được nhận</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((i) => {
                    const submitted = Object.entries(i.counts)
                      .filter(([s]) => s !== "DRAFT")
                      .reduce((sum, [, n]) => sum + n, 0);
                    return (
                      <tr key={i.id}>
                        <td data-label="Đợt tuyển">
                          <Link href={`/intakes/${i.id}`}>{i.name}</Link>
                          <div className="muted">{i.rounds.map((r) => r.label).join(" → ")}</div>
                        </td>
                        <td data-label="Trạng thái">
                          <StatusBadge entry={intakeStatus(i.status)} />
                        </td>
                        <td data-label="Thời gian">
                          {fmtDate(i.opens_at)} – {fmtDate(i.closes_at)}
                        </td>
                        <td data-label="Chỉ tiêu">{fmtNumber(i.quota)}</td>
                        <td data-label="Hồ sơ đã nộp">{fmtNumber(submitted)}</td>
                        <td data-label="Được nhận">{fmtNumber((i.counts["ACCEPTED"] ?? 0) + (i.counts["ENROLLED"] ?? 0))}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        }
      </QueryState>
      <Dialog open={open} title="Tạo đợt tuyển" size="lg" onClose={() => setOpen(false)}>
        <IntakeForm onClose={() => setOpen(false)} />
      </Dialog>
    </div>
  );
}
