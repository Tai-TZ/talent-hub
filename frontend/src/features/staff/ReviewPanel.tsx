"use client";

import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/Fields";
import { Progress } from "@/components/ui/Kit";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api";
import type { StaffApplication } from "@/lib/contracts";
import { fmtDateTime, fmtScore } from "@/lib/format";
import { errorText, useSend } from "@/lib/hooks";
import { RECOMMENDATIONS, recommendationLabel } from "@/lib/labels";
import { computeTotal } from "./evidence";

/** Thang điểm dạng nút chọn (nhanh hơn thanh trượt, phân biệt được "chưa chấm" với "0"); thang lớn hơn 10 dùng ô nhập số. */
export function ScorePicker({ name, label, help, max, value, onChange }: { name: string; label: string; help?: string; max: number; value: number | undefined; onChange: (v: number | undefined) => void }) {
  const options = Number.isInteger(max) && max <= 10 ? Array.from({ length: max + 1 }, (_, i) => i) : null;
  return (
    <fieldset className="plain-fieldset stack">
      <legend className="th-field__label score-legend">
        <span>{label}</span>
        <span className="muted">{value === undefined ? "chưa chấm" : `${value}/${max}`}</span>
      </legend>
      {help ? <span className="th-field__help">{help}</span> : null}
      {options ? (
        <div className="score-scale">
          {options.map((n) => (
            <label key={n} className="score-option">
              <input type="radio" name={`score-${name}`} value={n} checked={value === n} onChange={() => onChange(n)} />
              <span>{n}</span>
            </label>
          ))}
        </div>
      ) : (
        <input
          type="number"
          className="th-input"
          min={0}
          max={max}
          step={0.5}
          value={value ?? ""}
          aria-label={`Điểm ${label} (0 đến ${max})`}
          // Ô trống nghĩa là "chưa chấm": phải báo lên để xoá điểm, nếu không ô số bị kéo về giá trị cũ và không xoá được.
          onChange={(e) => onChange(e.target.value === "" ? undefined : Math.min(max, Math.max(0, Number(e.target.value))))}
        />
      )}
    </fieldset>
  );
}

interface Body {
  scores: Record<string, number>;
  comment: string;
  recommendation: string | null;
  submit: boolean;
}

export function ReviewPanel({ app, onChanged }: { app: StaffApplication; onChanged: () => void }) {
  const rubric = app.rubric;
  const mine = app.my_review;
  const submitted = mine?.submitted ?? false;
  const [scores, setScores] = useState<Record<string, number>>(mine?.scores ?? {});
  const [comment, setComment] = useState(mine?.comment ?? "");
  const [recommendation, setRecommendation] = useState<string | null>(mine?.recommendation ?? null);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string; fields?: Record<string, string> } | null>(null);
  const save = useSend<unknown, Body>("PUT", `/staff/applications/${app.id}/review`, { invalidate: ["/staff/applications"] });

  if (!rubric) return <Alert tone="warning">Vòng này chưa có rubric nên chưa thể chấm.</Alert>;

  const criteria = rubric.criteria;
  const total = computeTotal(criteria, scores);
  const scored = criteria.filter((c) => scores[c.id] !== undefined).length;
  const extremes = criteria.filter((c) => scores[c.id] === 0 || scores[c.id] === c.max);
  const commentShort = extremes.length > 0 && comment.trim().length < 20;
  const readyToSubmit = scored === criteria.length && recommendation !== null && !commentShort;

  function send(submit: boolean) {
    setMessage(null);
    save.mutate(
      { scores, comment, recommendation, submit },
      {
        onSuccess: () => {
          setMessage({ tone: "success", text: submit ? "Đã chốt điểm." : "Đã lưu nháp." });
          if (submit) onChanged();
        },
        onError: (e) => setMessage({ tone: "danger", text: errorText(e), fields: e instanceof ApiError ? e.fields : undefined }),
      },
    );
  }

  if (submitted) {
    return (
      <section className="th-card panel stack" aria-labelledby="review-title">
        <h2 id="review-title" className="th-type-h4">
          Điểm của bạn
        </h2>
        <p>
          Đã chốt: <strong className="score-chip">{fmtScore(mine?.total_score)}</strong> / 100
          {mine?.recommendation ? (
            <>
              {" "}
              · <StatusBadge entry={recommendationLabel(mine.recommendation)} />
            </>
          ) : null}
        </p>
        {mine?.comment ? <p className="record-text">{mine.comment}</p> : null}
      </section>
    );
  }

  return (
    <section id="review" className="th-card panel stack" aria-labelledby="review-title">
      <div className="row-actions">
        <h2 id="review-title" className="th-type-h4">
          Chấm điểm
        </h2>
        <span className="muted">
          Rubric v{rubric.version} · {scored}/{criteria.length} tiêu chí
        </span>
      </div>

      {criteria.map((c) => (
        <ScorePicker
          key={c.id}
          name={c.id}
          label={c.name}
          help={c.description || undefined}
          max={c.max}
          value={scores[c.id]}
          onChange={(v) =>
            setScores((prev) => {
              const next = { ...prev };
              if (v === undefined) delete next[c.id];
              else next[c.id] = v;
              return next;
            })
          }
        />
      ))}

      <div>
        <p className="muted">Điểm tổng tạm tính (trọng số theo rubric)</p>
        <p>
          <strong className="score-chip">{fmtScore(total)}</strong> / 100
        </p>
        <Progress value={total} label="Điểm tổng tạm tính" tone={total >= 70 ? "ok" : total >= 45 ? "warn" : "bad"} />
      </div>

      <fieldset className="plain-fieldset stack">
        <legend className="th-field__label">Khuyến nghị của bạn</legend>
        <div className="row-actions">
          {RECOMMENDATIONS.map((r) => (
            <label key={r} className="th-radio">
              <input type="radio" name="recommendation" checked={recommendation === r} onChange={() => setRecommendation(r)} />
              <span>{recommendationLabel(r)[0]}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <TextArea
        label="Nhận xét"
        rows={4}
        value={comment}
        maxLength={4000}
        error={message?.fields?.comment}
        help={commentShort ? "Có tiêu chí chấm tuyệt đối (0 hoặc tối đa): cần nhận xét ít nhất 20 ký tự để giải thích." : undefined}
        onChange={(e) => setComment(e.target.value)}
      />

      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}

      <div className="row-actions">
        <Button variant="secondary" onClick={() => send(false)} loading={save.isPending && !save.variables?.submit}>
          Lưu nháp
        </Button>
        <Button onClick={() => send(true)} loading={save.isPending && !!save.variables?.submit} disabled={!readyToSubmit}>
          Chốt điểm
        </Button>
      </div>
      <p className="muted">Sau khi chốt không thể sửa. Điểm của người chấm khác chỉ hiện sau khi bạn chốt (đánh giá độc lập).</p>
    </section>
  );
}

export function OtherReviews({ app }: { app: StaffApplication }) {
  if (app.reviews.length === 0) return null;
  return (
    <section className="th-card panel stack" aria-labelledby="others-title">
      <h2 id="others-title" className="th-type-h4">
        Các lượt chấm đã chốt
      </h2>
      {app.disagreement ? (
        <Alert tone="warning" title="Người chấm đang bất đồng">
          Có người khuyến nghị cho đi tiếp, có người khuyến nghị loại. Cần thêm một lượt chấm hoặc đề xuất quyết định có lý do.
        </Alert>
      ) : null}
      <ul className="plain-list stack">
        {app.reviews.map((r, i) => (
          <li key={i} className="stack">
            <div className="row-actions">
              <strong>{r.mine ? "Bạn" : (r.reviewer ?? `Người chấm ${i + 1}`)}</strong>
              <span className="score-chip">{fmtScore(r.total_score)}</span>
              {r.recommendation ? <StatusBadge entry={recommendationLabel(r.recommendation)} /> : null}
              <span className="muted">{fmtDateTime(r.submitted_at)}</span>
            </div>
            {r.comment ? <p className="record-text">{r.comment}</p> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
