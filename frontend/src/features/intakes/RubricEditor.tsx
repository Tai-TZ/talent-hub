"use client";

import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/Fields";
import { TextField } from "@/components/ui/TextField";
import type { Rubric } from "@/lib/contracts";
import { fmtPct } from "@/lib/format";
import { errorText, useSend } from "@/lib/hooks";
import { CRITERION_KINDS, type CriterionDraft, DEFAULT_RUBRIC, slugify, uniqueKey } from "./templates";

export function RubricEditor({ intakeId, round, rubric, locked }: { intakeId: string; round: string; rubric: Rubric | undefined; locked: boolean }) {
  const [criteria, setCriteria] = useState<CriterionDraft[]>(() =>
    rubric ? rubric.criteria.map((c) => ({ id: c.id, name: c.name, description: c.description, weight: c.weight, max: c.max, kind: c.kind })) : [],
  );
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const save = useSend<unknown, { criteria: CriterionDraft[] }>("PUT", `/intakes/${intakeId}/rubrics/${round}`, { invalidate: [`/intakes/${intakeId}`] });
  const total = criteria.reduce((sum, c) => sum + (c.weight || 0), 0);

  function patch(index: number, change: Partial<CriterionDraft>) {
    setCriteria((list) => list.map((c, i) => (i === index ? { ...c, ...change } : c)));
  }

  function add() {
    setCriteria((list) => {
      const id = uniqueKey("tieu_chi", list.map((c) => c.id));
      return [...list, { id, name: "", description: "", weight: 1, max: 5, kind: "custom" }];
    });
  }

  function submit() {
    setMessage(null);
    // Khoá tiêu chí mới sinh từ tên; tiêu chí đã có giữ nguyên khoá để lịch sử chấm không đổi nghĩa.
    const taken: string[] = [];
    const prepared = criteria.map((c) => {
      const existing = rubric?.criteria.some((x) => x.id === c.id);
      const id = existing ? c.id : uniqueKey(slugify(c.name || c.id, "tc"), [...taken, ...criteria.filter((o) => o !== c).map((o) => o.id)]);
      taken.push(id);
      return { ...c, id, name: c.name.trim(), description: c.description.trim() };
    });
    save.mutate(
      { criteria: prepared },
      {
        onSuccess: () => {
          setCriteria(prepared); // giữ khoá thật vừa lưu để lần sau không sinh lại khoá
          setMessage({ tone: "success", text: "Đã lưu rubric (phiên bản mới)." });
        },
        onError: (e) => setMessage({ tone: "danger", text: errorText(e) }),
      },
    );
  }

  return (
    <div className="stack">
      {locked ? <Alert tone="info">Vòng này đã có điểm được chốt nên không thể đổi rubric (giữ tính nhất quán giữa các ứng viên).</Alert> : null}
      {criteria.length === 0 ? (
        <Alert tone="warning" title="Vòng này chưa có rubric">
          Cần có rubric trước khi mở đợt tuyển.
          {!locked ? (
            <div style={{ marginTop: "var(--th-space-3)" }}>
              <Button size="sm" variant="secondary" onClick={() => setCriteria(DEFAULT_RUBRIC.map((c) => ({ ...c })))}>
                Dùng mẫu 7 tiêu chí
              </Button>
            </div>
          ) : null}
        </Alert>
      ) : null}

      {criteria.map((c, i) => (
        <fieldset key={c.id + i} className="row-card" disabled={locked}>
          <legend className="row-card__title">
            Tiêu chí {i + 1} · chiếm {fmtPct(total > 0 ? c.weight / total : 0)} điểm tổng
          </legend>
          <div className="row-card__grid">
            <TextField label="Tên tiêu chí" required value={c.name} maxLength={120} onChange={(e) => patch(i, { name: e.target.value })} />
            <SelectField label="Loại (AI dựa vào đây để đọc hồ sơ)" value={c.kind} onChange={(e) => patch(i, { kind: e.target.value })}>
              {CRITERION_KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </SelectField>
            <TextField label="Trọng số" type="number" min={0.5} max={10} step={0.5} value={String(c.weight)} onChange={(e) => patch(i, { weight: Number(e.target.value) })} />
            <TextField label="Điểm tối đa" type="number" min={1} max={100} value={String(c.max)} onChange={(e) => patch(i, { max: Number(e.target.value) })} />
            <TextField label="Mô tả cách chấm" value={c.description} maxLength={600} onChange={(e) => patch(i, { description: e.target.value })} />
          </div>
          {locked ? null : (
            <Button variant="tertiary" size="sm" onClick={() => setCriteria((list) => list.filter((_, j) => j !== i))}>
              Xoá tiêu chí
            </Button>
          )}
        </fieldset>
      ))}

      {locked ? null : (
        <div className="row-actions">
          <Button variant="secondary" onClick={add} disabled={criteria.length >= 20}>
            Thêm tiêu chí
          </Button>
          <Button onClick={submit} loading={save.isPending} disabled={criteria.length === 0 || criteria.some((c) => !c.name.trim() || !(c.weight > 0) || !(c.max > 0))}>
            Lưu rubric
          </Button>
        </div>
      )}
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
    </div>
  );
}
