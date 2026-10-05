"use client";

import type { ReactNode } from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import type { StaffApplication } from "@/lib/contracts";
import { markSegments } from "./evidence";

const GENDER: Record<string, string> = { female: "Nữ", male: "Nam", other: "Khác" };
const EDU_STATUS: Record<string, string> = { student: "Đang học", final_year: "Năm cuối", graduated: "Đã tốt nghiệp", other: "Khác" };

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="record-section" aria-label={title}>
      <h3 className="record-section__title">{title}</h3>
      {children}
    </section>
  );
}

function Marked({ text, quotes }: { text: string; quotes: string[] }) {
  return (
    <p className="record-text">
      {markSegments(text, quotes).map((seg, i) =>
        seg.mark ? (
          <mark key={i} className="evidence-mark">
            {seg.text}
          </mark>
        ) : (
          <span key={i}>{seg.text}</span>
        ),
      )}
    </p>
  );
}

/** Nội dung hồ sơ. `highlights` là các câu AI trích dẫn theo khoá trường (essays.motivation, ...). */
export function CandidateRecord({ app, highlights }: { app: StaffApplication; highlights: Record<string, string[]> }) {
  const c = app.content;
  const links = Object.entries(c.links).filter(([, v]) => v);
  return (
    <div className="stack">
      {app.flags.length > 0 ? (
        <Alert tone="warning" title="Cờ cần lưu ý">
          <ul className="plain-list">
            {app.flags.map((f, i) => (
              <li key={i}>{f.label}</li>
            ))}
          </ul>
        </Alert>
      ) : null}

      <Section title="Thông tin cá nhân">
        {app.profile ? (
          <dl className="summary">
            <div><dt>Họ tên</dt><dd>{app.profile.full_name || "—"}</dd></div>
            <div><dt>Điện thoại</dt><dd>{app.profile.phone ?? "—"}</dd></div>
            <div><dt>Ngày sinh</dt><dd>{app.profile.date_of_birth ?? "—"}</dd></div>
            <div><dt>Nơi ở</dt><dd>{app.profile.city ?? "—"}</dd></div>
            <div><dt>Giới tính</dt><dd>{app.profile.gender ? (GENDER[app.profile.gender] ?? app.profile.gender) : "—"}</dd></div>
          </dl>
        ) : (
          <p className="muted">Chấm mù: thông tin nhận dạng được ẩn để tránh thiên lệch. Bạn chỉ thấy phần năng lực.</p>
        )}
      </Section>

      <Section title="Học vấn">
        {c.education.length === 0 ? <p className="muted">Chưa khai.</p> : null}
        <ul className="plain-list stack">
          {c.education.map((e, i) => (
            <li key={i}>
              <strong>{e.school}</strong>
              <div className="muted">
                {[e.degree, e.major].filter(Boolean).join(" · ")} · {EDU_STATUS[e.status] ?? e.status}
                {e.year ? ` · ${e.year}` : ""}
                {e.gpa != null ? ` · GPA ${e.gpa}` : ""}
              </div>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Kinh nghiệm">
        {c.experience.length === 0 ? <p className="muted">Chưa khai.</p> : null}
        <ul className="plain-list stack">
          {c.experience.map((e, i) => (
            <li key={i}>
              <strong>{e.role || "Vai trò chưa nêu"}</strong> · {e.org}
              {e.years ? <span className="muted"> · {e.years} năm</span> : null}
              {e.description ? <p className="record-text">{e.description}</p> : null}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Dự án">
        {c.projects.length === 0 ? <p className="muted">Chưa khai.</p> : null}
        <ul className="plain-list stack">
          {c.projects.map((p, i) => (
            <li key={i}>
              <strong>{p.title}</strong>
              {p.link ? (
                <>
                  {" "}
                  ·{" "}
                  {p.link.startsWith("http") ? (
                    <a href={p.link} target="_blank" rel="noopener noreferrer">
                      liên kết
                    </a>
                  ) : (
                    <span className="muted">{p.link}</span>
                  )}
                </>
              ) : null}
              {p.description ? <p className="record-text">{p.description}</p> : null}
              {p.tech.length ? (
                <div className="badge-row">
                  {p.tech.map((t) => (
                    <Badge key={t}>{t}</Badge>
                  ))}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Kỹ năng">
        {c.skills.length === 0 ? <p className="muted">Chưa khai.</p> : null}
        <div className="badge-row">
          {c.skills.map((s) => (
            <Badge key={s}>{s}</Badge>
          ))}
        </div>
      </Section>

      <Section title="Bài luận">
        <h4 className="record-subtitle">Động lực tham gia</h4>
        {c.essays.motivation ? <Marked text={c.essays.motivation} quotes={highlights["essays.motivation"] ?? []} /> : <p className="muted">Chưa viết.</p>}
        {c.essays.problem_solving ? (
          <>
            <h4 className="record-subtitle">Giải quyết vấn đề</h4>
            <Marked text={c.essays.problem_solving} quotes={highlights["essays.problem_solving"] ?? []} />
          </>
        ) : null}
      </Section>

      {links.length > 0 ? (
        <Section title="Liên kết">
          <ul className="plain-list">
            {links.map(([name, url]) => (
              <li key={name}>
                {name}:{" "}
                {url?.startsWith("http") ? (
                  <a href={url} target="_blank" rel="noopener noreferrer">
                    {url}
                  </a>
                ) : (
                  <span className="muted">{url}</span>
                )}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {c.cv_text ? (
        <details className="record-section">
          <summary>Nội dung CV</summary>
          <p className="record-text">{c.cv_text}</p>
        </details>
      ) : null}
    </div>
  );
}
