"use client";

import { useDeferredValue, useState } from "react";
import { useMe } from "@/components/providers";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { SelectField } from "@/components/ui/Fields";
import { Pager } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { TextField } from "@/components/ui/TextField";
import type { CohortOverview, Enrollment, EnrollmentPage } from "@/lib/contracts";
import { fmtDate, fmtNumber } from "@/lib/format";
import { errorText, useGet, useSend } from "@/lib/hooks";
import { enrollmentStatus } from "@/lib/labels";

const LIMIT = 25;

function AssignForm({ enrollment, overview, onClose }: { enrollment: Enrollment; overview: CohortOverview; onClose: () => void }) {
  const [classId, setClassId] = useState(enrollment.class_id ?? "");
  const [trackId, setTrackId] = useState(enrollment.track_id ?? "");
  const [error, setError] = useState<string | null>(null);
  const save = useSend<unknown, { class_id: string | null; track_id: string | null }>("PATCH", `/enrollments/${enrollment.id}`, { invalidate: ["/cohorts"] });
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate({ class_id: classId || null, track_id: trackId || null }, { onSuccess: onClose, onError: (err) => setError(errorText(err)) });
      }}
    >
      <p>
        <strong>{enrollment.name}</strong> · <span className="mono">{enrollment.candidate_code}</span>
      </p>
      <SelectField label="Lớp" value={classId} onChange={(e) => setClassId(e.target.value)}>
        <option value="">Chưa xếp lớp</option>
        {overview.classes.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name} ({c.assigned}/{c.capacity})
          </option>
        ))}
      </SelectField>
      <SelectField label="Nhánh" value={trackId} onChange={(e) => setTrackId(e.target.value)}>
        <option value="">Chưa chọn nhánh</option>
        {overview.tracks.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name["vi"] ?? t.key} ({t.assigned}/{t.capacity ?? "—"})
          </option>
        ))}
      </SelectField>
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="dialog__actions">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button type="submit" loading={save.isPending}>
          Lưu
        </Button>
      </div>
    </form>
  );
}

export function EnrollmentsTab({ cohortId }: { cohortId: string }) {
  const me = useMe();
  const canManage = me.permissions.includes("cohort.manage");
  const overview = useGet<CohortOverview>(`/cohorts/${cohortId}/overview`);
  const [status, setStatus] = useState("");
  const [classId, setClassId] = useState("");
  const [trackId, setTrackId] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<Enrollment | null>(null);
  const q = useDeferredValue(search.trim());

  const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
  if (status) params.set("status", status);
  if (classId) params.set("class_id", classId);
  if (trackId) params.set("track_id", trackId);
  if (q) params.set("q", q);
  const list = useGet<EnrollmentPage>(`/cohorts/${cohortId}/enrollments?${params}`);

  const className = (id: string | null) => overview.data?.classes.find((c) => c.id === id)?.name ?? "—";
  const trackName = (id: string | null) => {
    const t = overview.data?.tracks.find((x) => x.id === id);
    return t ? (t.name["vi"] ?? t.key) : "—";
  };
  const reset = (fn: () => void) => () => {
    fn();
    setOffset(0);
  };

  return (
    <div className="stack">
      <div className="toolbar">
        <TextField label="Tìm theo tên, email, mã hồ sơ" type="search" value={search} onChange={(e) => reset(() => setSearch(e.target.value))()} />
        <SelectField label="Trạng thái" value={status} onChange={(e) => reset(() => setStatus(e.target.value))()}>
          <option value="">Tất cả</option>
          {["active", "qualified", "not_qualified", "withdrawn"].map((s) => (
            <option key={s} value={s}>
              {enrollmentStatus(s)[0]}
            </option>
          ))}
        </SelectField>
        <SelectField label="Lớp" value={classId} onChange={(e) => reset(() => setClassId(e.target.value))()}>
          <option value="">Tất cả</option>
          {overview.data?.classes.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </SelectField>
        <SelectField label="Nhánh" value={trackId} onChange={(e) => reset(() => setTrackId(e.target.value))()}>
          <option value="">Tất cả</option>
          {overview.data?.tracks.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name["vi"] ?? t.key}
            </option>
          ))}
        </SelectField>
      </div>

      <QueryState query={list} lines={6}>
        {(page) =>
          page.items.length === 0 ? (
            <EmptyState title="Không có học viên phù hợp" />
          ) : (
            <>
              <p className="muted" aria-live="polite">
                {fmtNumber(page.total)} học viên
              </p>
              <div className="table-wrap">
                <table className="th-table responsive-table">
                  <thead>
                    <tr>
                      <th scope="col">Học viên</th>
                      <th scope="col">Mã hồ sơ</th>
                      <th scope="col">Trạng thái</th>
                      <th scope="col">Lớp</th>
                      <th scope="col">Nhánh</th>
                      <th scope="col">Ghi danh</th>
                      {canManage ? <th scope="col">Thao tác</th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((e) => (
                      <tr key={e.id}>
                        <td data-label="Học viên">
                          {e.name}
                          <div className="muted">{e.email}</div>
                        </td>
                        <td data-label="Mã hồ sơ" className="mono">
                          {e.candidate_code}
                        </td>
                        <td data-label="Trạng thái">
                          <StatusBadge entry={enrollmentStatus(e.status)} />
                        </td>
                        <td data-label="Lớp">{className(e.class_id)}</td>
                        <td data-label="Nhánh">{trackName(e.track_id)}</td>
                        <td data-label="Ghi danh">{fmtDate(e.enrolled_at)}</td>
                        {canManage ? (
                          <td data-label="Thao tác">
                            {overview.data && e.status === "active" ? (
                              <Button variant="tertiary" size="sm" onClick={() => setEditing(e)}>
                                Xếp lớp/nhánh
                              </Button>
                            ) : null}
                          </td>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pager total={page.total} offset={offset} limit={LIMIT} onChange={setOffset} label="Phân trang học viên" />
            </>
          )
        }
      </QueryState>

      <Dialog open={editing !== null} title="Xếp lớp và nhánh" size="sm" onClose={() => setEditing(null)}>
        {editing && overview.data ? <AssignForm enrollment={editing} overview={overview.data} onClose={() => setEditing(null)} /> : null}
      </Dialog>
    </div>
  );
}
