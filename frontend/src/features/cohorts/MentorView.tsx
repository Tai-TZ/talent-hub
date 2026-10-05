"use client";

import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { SelectField, TextArea } from "@/components/ui/Fields";
import { PageHeader, Progress } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Competencies, MentorLearner } from "@/lib/contracts";
import { errorText, useGet, useSend } from "@/lib/hooks";
import { suggestionLabel } from "@/lib/labels";

type Row = Competencies["matrix"][number];

function AssessForm({ enrollmentId, row, onClose }: { enrollmentId: string; row: Row; onClose: () => void }) {
  const [level, setLevel] = useState(String(row.level ?? Math.min(row.target, row.max_level)));
  const [evidence, setEvidence] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useSend<unknown, { competency_id: string; level: number; evidence: string }>("POST", `/enrollments/${enrollmentId}/assessments`, { invalidate: ["/enrollments", "/cohorts"] });
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate({ competency_id: row.competency_id, level: Number(level), evidence }, { onSuccess: onClose, onError: (err) => setError(errorText(err)) });
      }}
    >
      <p>
        <strong>{row.name}</strong> · chuẩn của nhánh: mức {row.target}/{row.max_level}
      </p>
      <SelectField label="Mức đánh giá" value={level} onChange={(e) => setLevel(e.target.value)}>
        {Array.from({ length: row.max_level }, (_, i) => i + 1).map((n) => (
          <option key={n} value={n}>
            Mức {n}
            {n === row.target ? " (đạt chuẩn)" : ""}
          </option>
        ))}
      </SelectField>
      <TextArea label="Bằng chứng" required rows={4} value={evidence} maxLength={2000} onChange={(e) => setEvidence(e.target.value)} help="Nêu việc học viên đã làm được, sản phẩm hoặc quan sát cụ thể. Tối thiểu 15 ký tự." />
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="dialog__actions">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button type="submit" loading={save.isPending} disabled={evidence.trim().length < 15}>
          Lưu đánh giá
        </Button>
      </div>
    </form>
  );
}

function LearnerPanel({ learner }: { learner: MentorLearner }) {
  const query = useGet<Competencies>(`/enrollments/${learner.enrollment_id}/competencies`);
  const [editing, setEditing] = useState<Row | null>(null);
  return (
    <QueryState query={query} lines={4}>
      {(c) => (
        <div className="stack">
          <p className="row-actions">
            <StatusBadge entry={suggestionLabel(c.suggestion)} />
            <span className="muted">Gợi ý này tính từ dữ liệu đánh giá; quyết định đạt/chưa đạt do người quản lý đào tạo.</span>
          </p>
          {c.matrix.length === 0 ? (
            <Alert tone="info">Nhánh của học viên chưa có chuẩn năng lực, hoặc học viên chưa được gán nhánh.</Alert>
          ) : (
            <ul className="plain-list stack">
              {c.matrix.map((m) => (
                <li key={m.competency_id} className="ai-criterion">
                  <div className="row-actions">
                    <strong>{m.name}</strong>
                    <span className="muted">
                      {m.level ?? "chưa đánh giá"} / chuẩn {m.target}
                    </span>
                    {m.met === true ? <StatusBadge entry={["Đạt chuẩn", "success"]} /> : m.met === false ? <StatusBadge entry={["Chưa đạt chuẩn", "danger"]} /> : null}
                  </div>
                  <Progress value={m.level ?? 0} max={m.max_level} label={`Mức năng lực ${m.name}`} tone={m.met === true ? "ok" : m.met === false ? "warn" : undefined} />
                  {m.evidence ? <p className="muted">Bằng chứng gần nhất: {m.evidence}</p> : null}
                  <div>
                    <Button variant="secondary" size="sm" onClick={() => setEditing(m)}>
                      Đánh giá
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <Dialog open={editing !== null} title="Đánh giá năng lực" size="sm" onClose={() => setEditing(null)}>
            {editing ? <AssessForm enrollmentId={learner.enrollment_id} row={editing} onClose={() => setEditing(null)} /> : null}
          </Dialog>
        </div>
      )}
    </QueryState>
  );
}

export function MentorView() {
  const learners = useGet<MentorLearner[]>("/mentor/learners");
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <div className="stack">
      <PageHeader title="Học viên của tôi" subtitle="Đánh giá mức năng lực của học viên bạn phụ trách. Mỗi đánh giá cần kèm bằng chứng cụ thể." />
      <QueryState query={learners} lines={4}>
        {(list) => {
          if (list.length === 0) return <EmptyState title="Bạn chưa được giao học viên nào" />;
          const current = list.find((l) => l.enrollment_id === selected) ?? list[0]!;
          return (
            <div className="split split--list">
              <nav aria-label="Danh sách học viên" className="th-card panel">
                <ul className="plain-list stack">
                  {list.map((l) => (
                    <li key={l.enrollment_id}>
                      <button type="button" className="nav-link" aria-current={l.enrollment_id === current.enrollment_id ? "page" : undefined} onClick={() => setSelected(l.enrollment_id)}>
                        {l.name}
                      </button>
                    </li>
                  ))}
                </ul>
              </nav>
              <section className="th-card panel stack" aria-labelledby="learner-detail">
                <h2 id="learner-detail" className="th-type-h4">
                  {current.name}
                </h2>
                <p className="muted">
                  {current.track_name ?? "Chưa gán nhánh"} · {current.partner_name}
                  {current.project ? ` · ${current.project}` : ""}
                </p>
                <LearnerPanel key={current.enrollment_id} learner={current} />
              </section>
            </div>
          );
        }}
      </QueryState>
    </div>
  );
}
