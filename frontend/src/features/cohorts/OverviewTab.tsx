"use client";

import { useState } from "react";
import { useMe } from "@/components/providers";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { BarList, Stat } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { TextField } from "@/components/ui/TextField";
import type { CohortOverview } from "@/lib/contracts";
import { fmtNumber } from "@/lib/format";
import { errorText, useGet, useSend } from "@/lib/hooks";

function ClassForm({ cohortId, onClose }: { cohortId: string; onClose: () => void }) {
  const [name, setName] = useState("");
  const [level, setLevel] = useState("1");
  const [capacity, setCapacity] = useState("40");
  const [error, setError] = useState<string | null>(null);
  const create = useSend<unknown, { name: string; level: number; capacity: number }>("POST", `/cohorts/${cohortId}/classes`, { invalidate: ["/cohorts"] });
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate({ name: name.trim(), level: Number(level), capacity: Number(capacity) }, { onSuccess: onClose, onError: (err) => setError(errorText(err)) });
      }}
    >
      <TextField label="Tên lớp" required value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
      <div className="form-grid">
        <TextField label="Mức" type="number" min={1} max={20} required value={level} onChange={(e) => setLevel(e.target.value)} help="Lớp mức 1 là nền tảng." />
        <TextField label="Sĩ số tối đa" type="number" min={1} required value={capacity} onChange={(e) => setCapacity(e.target.value)} />
      </div>
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="dialog__actions">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button type="submit" loading={create.isPending} disabled={!name.trim()}>
          Tạo lớp
        </Button>
      </div>
    </form>
  );
}

export function OverviewTab({ cohortId }: { cohortId: string }) {
  const me = useMe();
  const canManage = me.permissions.includes("cohort.manage");
  const query = useGet<CohortOverview>(`/cohorts/${cohortId}/overview`);
  const [classOpen, setClassOpen] = useState(false);
  const [message, setMessage] = useState<{ tone: "info" | "danger"; text: string } | null>(null);
  const enroll = useSend<{ enrolled: number }>("POST", `/cohorts/${cohortId}/enroll-accepted`, { invalidate: ["/cohorts", "/intakes", "/staff"] });

  return (
    <QueryState query={query} lines={5}>
      {(o) => {
        const active = o.enrollments["active"] ?? 0;
        const total = Object.values(o.enrollments).reduce((a, b) => a + b, 0);
        return (
          <div className="stack">
            <div className="stat-grid">
              <Stat label="Sức chứa khoá" value={fmtNumber(o.cohort.capacity)} hint={`${fmtNumber(total)} học viên đã ghi danh`} />
              <Stat label="Đang học" value={fmtNumber(active)} />
              <Stat label="Đạt yêu cầu" value={fmtNumber(o.enrollments["qualified"] ?? 0)} tone="ok" />
              <Stat label="Chưa đạt" value={fmtNumber(o.enrollments["not_qualified"] ?? 0)} tone={(o.enrollments["not_qualified"] ?? 0) > 0 ? "warn" : undefined} />
              <Stat label="Chưa có nơi thực chiến" value={fmtNumber(o.unplaced)} tone={o.unplaced > 0 ? "warn" : "ok"} hint="Học viên đang học chưa gán đối tác" />
            </div>

            {o.accepted_waiting_enrollment > 0 ? (
              <Alert tone="info" title={`${fmtNumber(o.accepted_waiting_enrollment)} hồ sơ đã được nhận, chờ ghi danh`}>
                Ghi danh biến hồ sơ trúng tuyển thành học viên của khoá này.
                {canManage ? (
                  <div style={{ marginTop: "var(--th-space-3)" }}>
                    <Button
                      size="sm"
                      loading={enroll.isPending}
                      onClick={() => {
                        setMessage(null);
                        enroll.mutate(undefined, {
                          onSuccess: (r) => setMessage({ tone: "info", text: `Đã ghi danh ${fmtNumber(r.enrolled)} học viên.` }),
                          onError: (e) => setMessage({ tone: "danger", text: errorText(e) }),
                        });
                      }}
                    >
                      Ghi danh tất cả
                    </Button>
                  </div>
                ) : null}
              </Alert>
            ) : null}
            {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}

            <div className="split split--2">
              <section className="th-card panel stack" aria-labelledby="class-title">
                <div className="row-actions">
                  <h2 id="class-title" className="th-type-h4">
                    Lớp học
                  </h2>
                  {canManage ? (
                    <Button variant="secondary" size="sm" onClick={() => setClassOpen(true)}>
                      Thêm lớp
                    </Button>
                  ) : null}
                </div>
                {o.classes.length === 0 ? (
                  <p className="muted">Chưa có lớp. Dùng Cohort Composer để xếp lớp tự động hoặc tạo lớp thủ công.</p>
                ) : (
                  <BarList rows={o.classes.map((c) => ({ label: c.name, value: c.assigned, hint: `/ ${c.capacity}`, tone: c.assigned > c.capacity ? "bad" : "info" }))} />
                )}
              </section>
              <section className="th-card panel stack" aria-labelledby="track-title">
                <h2 id="track-title" className="th-type-h4">
                  Nhánh học
                </h2>
                <BarList
                  rows={o.tracks.map((t) => ({
                    label: t.name["vi"] ?? t.key,
                    value: t.assigned,
                    hint: t.capacity != null ? `/ ${t.capacity}` : "chưa đặt sức chứa",
                    tone: t.capacity != null && t.assigned > t.capacity ? "bad" : "info",
                  }))}
                />
              </section>
            </div>

            <Dialog open={classOpen} title="Thêm lớp học" size="sm" onClose={() => setClassOpen(false)}>
              <ClassForm cohortId={cohortId} onClose={() => setClassOpen(false)} />
            </Dialog>
          </div>
        );
      }}
    </QueryState>
  );
}
