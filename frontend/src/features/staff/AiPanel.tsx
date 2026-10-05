"use client";

import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Progress } from "@/components/ui/Kit";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { AiAssessment, AiLocked, Criterion, StaffApplication } from "@/lib/contracts";
import { fmtPct, fmtScore } from "@/lib/format";
import { tierLabel } from "@/lib/labels";
import { fieldLabel, fieldTexts, snippetOf } from "./evidence";

function isLocked(ai: AiAssessment | AiLocked): ai is AiLocked {
  return ai.locked === true;
}

function Evidence({ ai, criterionId, texts }: { ai: AiAssessment; criterionId: string; texts: Record<string, string> }) {
  const items = ai.evidence[criterionId] ?? [];
  if (items.length === 0) return <p className="muted">AI không tìm thấy trích dẫn nào cho tiêu chí này.</p>;
  return (
    <ul className="plain-list stack">
      {items.map((e, i) => {
        const snip = snippetOf(texts[e.field], e.quote);
        return (
          <li key={i}>
            <blockquote className="quote">
              {snip ? (
                <>
                  <span className="muted">{snip.before}</span>
                  <mark className="evidence-mark">{snip.quote}</mark>
                  <span className="muted">{snip.after}</span>
                </>
              ) : (
                <mark className="evidence-mark">{e.quote}</mark>
              )}
              <cite>{fieldLabel(e.field)}</cite>
            </blockquote>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Gợi ý của AI. Chống neo: người chấm chưa chốt điểm chỉ thấy cờ trung tính. Mọi bằng chứng đều là câu có thật trong hồ sơ
 * (BE kiểm chứng nguyên văn), AI không quyết định kết quả.
 */
export function AiPanel({
  ai,
  app,
  criteria,
  active,
  onActivate,
}: {
  ai: AiAssessment | AiLocked;
  app: StaffApplication;
  criteria: Criterion[];
  active: string | null;
  onActivate: (criterionId: string | null) => void;
}) {
  const [open, setOpen] = useState<string | null>(null);

  if (isLocked(ai)) {
    return (
      <section className="th-card panel stack" aria-labelledby="ai-title">
        <h2 id="ai-title" className="th-type-h4">
          Gợi ý AI
        </h2>
        <Alert tone="info" title="Gợi ý AI đang được ẩn">
          Hãy chốt điểm của bạn trước. Cách làm này tránh để AI neo ý kiến của người chấm (điểm hai bên độc lập, sau đó mới đối chiếu).
        </Alert>
        {ai.needs_attention ? <StatusBadge entry={["AI đánh dấu: ưu tiên xem kỹ", "warning"]} /> : null}
      </section>
    );
  }

  const texts = fieldTexts(app.content);
  const byId = new Map(criteria.map((c) => [c.id, c]));
  return (
    <section className="th-card panel stack" aria-labelledby="ai-title">
      <div className="row-actions">
        <h2 id="ai-title" className="th-type-h4">
          Gợi ý AI
        </h2>
        <StatusBadge entry={tierLabel(ai.tier)} />
        {ai.needs_attention ? <StatusBadge entry={["Ưu tiên xem kỹ", "warning"]} /> : null}
      </div>
      <p>
        Điểm gợi ý <strong className="score-chip">{fmtScore(ai.total_score)}</strong> / 100 · độ tin cậy {fmtPct(ai.confidence)}
      </p>
      <p className="record-text">{ai.rationale}</p>

      {ai.flags.length > 0 ? (
        <Alert tone="warning" title="AI ghi nhận">
          <ul className="plain-list">
            {ai.flags.map((f, i) => (
              <li key={i}>{f.label}</li>
            ))}
          </ul>
        </Alert>
      ) : null}

      <ul className="plain-list stack">
        {Object.entries(ai.scores).map(([id, s]) => {
          const crit = byId.get(id);
          const expanded = open === id;
          return (
            <li key={id} className={`ai-criterion ${active === id ? "ai-criterion--active" : ""}`}>
              <div className="row-actions">
                <strong>{crit?.name ?? id}</strong>
                <span className="muted">
                  {s.score}/{s.max} · tin cậy {fmtPct(s.confidence)}
                </span>
              </div>
              <Progress value={s.score} max={s.max} label={`Điểm AI cho ${crit?.name ?? id}`} />
              <p className="muted">{s.rationale}</p>
              <button
                type="button"
                className="link-button"
                aria-expanded={expanded}
                onClick={() => {
                  setOpen(expanded ? null : id);
                  onActivate(expanded ? null : id);
                }}
              >
                {expanded ? "Ẩn bằng chứng" : `Xem bằng chứng (${ai.evidence[id]?.length ?? 0})`}
              </button>
              {expanded ? <Evidence ai={ai} criterionId={id} texts={texts} /> : null}
            </li>
          );
        })}
      </ul>

      <p className="muted">
        Động cơ: {ai.engine}
        {ai.model ? ` · ${ai.model}` : ""} · prompt {ai.prompt_version}. Chỉ phần năng lực ({ai.input_fields.length} trường) được đưa vào AI; họ tên, giới tính, ngày sinh và nơi ở không được dùng.
        AI chỉ gợi ý, người chấm và người phê duyệt quyết định.
      </p>
    </section>
  );
}
