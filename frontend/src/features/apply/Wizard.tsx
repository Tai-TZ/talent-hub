"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Checkbox, SelectField, TextArea } from "@/components/ui/Fields";
import { TextField } from "@/components/ui/TextField";
import { api, ApiError } from "@/lib/api";
import type { ApplicationView, Track } from "@/lib/contracts";
import { FIELD_LABELS } from "@/lib/labels";
import { errorText } from "@/lib/hooks";
import { type Draft, draftFromView, MIN_ESSAY_CHARS, STEPS, type StepKey, stepOfField, toPayload } from "./draft";

type SaveState = { kind: "idle" } | { kind: "saving" } | { kind: "saved"; at: Date } | { kind: "error"; message: string };

function RowCard({ title, onRemove, children }: { title: string; onRemove: () => void; children: ReactNode }) {
  return (
    <fieldset className="row-card">
      <legend className="row-card__title">{title}</legend>
      <div className="row-card__grid">{children}</div>
      <Button variant="tertiary" size="sm" onClick={onRemove}>
        Xoá mục này
      </Button>
    </fieldset>
  );
}

function update<K extends keyof Draft>(draft: Draft, key: K, value: Draft[K]): Draft {
  return { ...draft, [key]: value };
}

function replaceAt<T>(list: T[], index: number, patch: Partial<T>): T[] {
  return list.map((item, i) => (i === index ? { ...item, ...patch } : item));
}

/** `infoOnly`: ứng viên chỉ chỉnh sửa theo yêu cầu bổ sung; lưu xong quay lại màn hình tình trạng để bấm "Gửi lại". */
export function Wizard({
  view,
  tracks,
  onSubmitted,
  infoOnly = false,
}: {
  view: ApplicationView;
  tracks: Track[];
  onSubmitted: () => void;
  infoOnly?: boolean;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftFromView(view));
  const [step, setStep] = useState<StepKey>("profile");
  const [save, setSave] = useState<SaveState>({ kind: "idle" });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [consent, setConsent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const dirty = useRef(false);
  const first = useRef(true);

  const payload = useMemo(() => toPayload(draft), [draft]);
  const payloadJson = JSON.stringify(payload);

  async function persist(): Promise<boolean> {
    setSave({ kind: "saving" });
    try {
      await api(`/applications/${view.id}`, { method: "PATCH", json: payload });
      dirty.current = false;
      setSave({ kind: "saved", at: new Date() });
      setFieldErrors({});
      return true;
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) setFieldErrors(error.fields);
      setSave({ kind: "error", message: errorText(error, "Chưa lưu được bản nháp") });
      return false;
    }
  }

  // Tự lưu sau 1,2 giây ngừng gõ.
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    dirty.current = true;
    const timer = setTimeout(() => void persist(), 1200);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payloadJson]);

  // Cảnh báo khi rời trang lúc còn thay đổi chưa lưu.
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty.current) e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  const stepIndex = STEPS.findIndex((s) => s.key === step);
  const err = (path: string) => fieldErrors[path];
  const essayLength = draft.essays.motivation.trim().length;

  async function submit() {
    setSubmitError(null);
    setSubmitting(true);
    try {
      if (!(await persist())) return;
      if (infoOnly) {
        dirty.current = false;
        onSubmitted();
        return;
      }
      await api(`/applications/${view.id}/submit`, { method: "POST", json: { consent, version: view.version } });
      dirty.current = false;
      onSubmitted();
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        setFieldErrors(error.fields);
        setSubmitError(error.message);
      } else {
        setSubmitError(errorText(error, "Chưa nộp được hồ sơ"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  const missing = Object.entries(fieldErrors).filter(([path]) => path !== "consent");

  return (
    <div className="stack">
      <ol className="wizard-steps" aria-label="Các bước nộp hồ sơ">
        {STEPS.map((s, i) => (
          <li key={s.key}>
            <button type="button" className="wizard-step" aria-current={s.key === step ? "step" : undefined} onClick={() => setStep(s.key)}>
              <span aria-hidden="true">{i + 1}.</span> {s.label}
            </button>
          </li>
        ))}
      </ol>

      <p className="muted" role="status" aria-live="polite">
        {save.kind === "saving" && "Đang lưu…"}
        {save.kind === "saved" && `Đã lưu bản nháp lúc ${save.at.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`}
        {save.kind === "error" && save.message}
        {save.kind === "idle" && "Bản nháp tự động lưu khi bạn nhập."}
      </p>

      <section className="th-card panel panel--form stack" aria-labelledby="step-title">
        <h2 id="step-title" className="th-type-h3">
          {STEPS[stepIndex]?.label}
        </h2>

        {step === "profile" && (
          <div className="form-grid">
            <TextField label="Họ và tên" required value={draft.profile.full_name} error={err("profile.full_name")} autoComplete="name" onChange={(e) => setDraft(update(draft, "profile", { ...draft.profile, full_name: e.target.value }))} />
            <TextField label="Số điện thoại" required type="tel" autoComplete="tel" value={draft.profile.phone} error={err("profile.phone")} onChange={(e) => setDraft(update(draft, "profile", { ...draft.profile, phone: e.target.value }))} />
            <TextField label="Ngày sinh" type="date" value={draft.profile.date_of_birth} error={err("profile.date_of_birth")} onChange={(e) => setDraft(update(draft, "profile", { ...draft.profile, date_of_birth: e.target.value }))} />
            <TextField label="Tỉnh/thành phố" value={draft.profile.city} autoComplete="address-level1" onChange={(e) => setDraft(update(draft, "profile", { ...draft.profile, city: e.target.value }))} />
            <SelectField label="Giới tính (không bắt buộc)" value={draft.profile.gender} help="Chỉ dùng để thống kê công bằng gộp nhóm, không dùng để chấm điểm." onChange={(e) => setDraft(update(draft, "profile", { ...draft.profile, gender: e.target.value }))}>
              <option value="">Không muốn nêu</option>
              <option value="female">Nữ</option>
              <option value="male">Nam</option>
              <option value="other">Khác</option>
            </SelectField>
          </div>
        )}

        {step === "education" && (
          <>
            {err("content.education") ? <Alert tone="danger">{err("content.education")}</Alert> : null}
            {draft.education.map((e, i) => (
              <RowCard key={i} title={`Học vấn ${i + 1}`} onRemove={() => setDraft(update(draft, "education", draft.education.filter((_, j) => j !== i)))}>
                <TextField label="Trường" required value={e.school} onChange={(ev) => setDraft(update(draft, "education", replaceAt(draft.education, i, { school: ev.target.value })))} />
                <TextField label="Ngành học" value={e.major} onChange={(ev) => setDraft(update(draft, "education", replaceAt(draft.education, i, { major: ev.target.value })))} />
                <TextField label="Bậc/Bằng cấp" value={e.degree} onChange={(ev) => setDraft(update(draft, "education", replaceAt(draft.education, i, { degree: ev.target.value })))} />
                <SelectField label="Tình trạng" value={e.status} onChange={(ev) => setDraft(update(draft, "education", replaceAt(draft.education, i, { status: ev.target.value })))}>
                  <option value="student">Đang học</option>
                  <option value="final_year">Năm cuối</option>
                  <option value="graduated">Đã tốt nghiệp</option>
                  <option value="other">Khác</option>
                </SelectField>
                <TextField label="Năm" inputMode="numeric" value={e.year} onChange={(ev) => setDraft(update(draft, "education", replaceAt(draft.education, i, { year: ev.target.value })))} />
                <TextField label="GPA (thang 10)" inputMode="decimal" value={e.gpa} onChange={(ev) => setDraft(update(draft, "education", replaceAt(draft.education, i, { gpa: ev.target.value })))} />
              </RowCard>
            ))}
            <div>
              <Button variant="secondary" onClick={() => setDraft(update(draft, "education", [...draft.education, { school: "", degree: "", major: "", status: "student", year: "", gpa: "" }]))}>
                Thêm học vấn
              </Button>
            </div>
          </>
        )}

        {step === "work" && (
          <>
            <h3 className="th-type-h4">Kinh nghiệm</h3>
            {draft.experience.map((e, i) => (
              <RowCard key={i} title={`Kinh nghiệm ${i + 1}`} onRemove={() => setDraft(update(draft, "experience", draft.experience.filter((_, j) => j !== i)))}>
                <TextField label="Tổ chức" required value={e.org} onChange={(ev) => setDraft(update(draft, "experience", replaceAt(draft.experience, i, { org: ev.target.value })))} />
                <TextField label="Vai trò" value={e.role} onChange={(ev) => setDraft(update(draft, "experience", replaceAt(draft.experience, i, { role: ev.target.value })))} />
                <TextField label="Số năm" inputMode="decimal" value={e.years} onChange={(ev) => setDraft(update(draft, "experience", replaceAt(draft.experience, i, { years: ev.target.value })))} />
                <TextArea label="Mô tả công việc" rows={3} value={e.description} onChange={(ev) => setDraft(update(draft, "experience", replaceAt(draft.experience, i, { description: ev.target.value })))} />
              </RowCard>
            ))}
            <div>
              <Button variant="secondary" onClick={() => setDraft(update(draft, "experience", [...draft.experience, { org: "", role: "", years: "", description: "" }]))}>
                Thêm kinh nghiệm
              </Button>
            </div>
            <h3 className="th-type-h4">Dự án</h3>
            {draft.projects.map((p, i) => (
              <RowCard key={i} title={`Dự án ${i + 1}`} onRemove={() => setDraft(update(draft, "projects", draft.projects.filter((_, j) => j !== i)))}>
                <TextField label="Tên dự án" required value={p.title} onChange={(ev) => setDraft(update(draft, "projects", replaceAt(draft.projects, i, { title: ev.target.value })))} />
                <TextField label="Đường dẫn" type="url" placeholder="https://" value={p.link} onChange={(ev) => setDraft(update(draft, "projects", replaceAt(draft.projects, i, { link: ev.target.value })))} />
                <TextField label="Công nghệ (cách nhau bởi dấu phẩy)" value={p.tech} onChange={(ev) => setDraft(update(draft, "projects", replaceAt(draft.projects, i, { tech: ev.target.value })))} />
                <TextArea label="Mô tả (vai trò của bạn, kết quả đạt được)" rows={4} value={p.description} onChange={(ev) => setDraft(update(draft, "projects", replaceAt(draft.projects, i, { description: ev.target.value })))} />
              </RowCard>
            ))}
            <div>
              <Button variant="secondary" onClick={() => setDraft(update(draft, "projects", [...draft.projects, { title: "", description: "", link: "", tech: "" }]))}>
                Thêm dự án
              </Button>
            </div>
          </>
        )}

        {step === "skills" && (
          <>
            <TextArea label="Kỹ năng (cách nhau bởi dấu phẩy)" required rows={3} value={draft.skills} error={err("content.skills")} help="Ví dụ: Python, SQL, học máy, phân tích dữ liệu" onChange={(e) => setDraft(update(draft, "skills", e.target.value))} />
            <div className="form-grid">
              <TextField label="GitHub" type="url" placeholder="https://github.com/…" value={draft.links.github} error={err("content.links.github")} onChange={(e) => setDraft(update(draft, "links", { ...draft.links, github: e.target.value }))} />
              <TextField label="LinkedIn" type="url" placeholder="https://linkedin.com/in/…" value={draft.links.linkedin} error={err("content.links.linkedin")} onChange={(e) => setDraft(update(draft, "links", { ...draft.links, linkedin: e.target.value }))} />
              <TextField label="Portfolio" type="url" placeholder="https://" value={draft.links.portfolio} error={err("content.links.portfolio")} onChange={(e) => setDraft(update(draft, "links", { ...draft.links, portfolio: e.target.value }))} />
            </div>
            <TextArea label="Nội dung CV (dán văn bản, không bắt buộc)" rows={6} value={draft.cv_text} onChange={(e) => setDraft(update(draft, "cv_text", e.target.value))} />
          </>
        )}

        {step === "essays" && (
          <>
            <TextArea
              label="Vì sao bạn muốn tham gia chương trình?"
              required
              rows={7}
              value={draft.essays.motivation}
              error={err("content.essays.motivation")}
              help={`${essayLength}/${MIN_ESSAY_CHARS} ký tự tối thiểu. Hãy kể điều cụ thể bạn đã làm, không chỉ nói mong muốn.`}
              onChange={(e) => setDraft(update(draft, "essays", { ...draft.essays, motivation: e.target.value }))}
            />
            <TextArea
              label="Một vấn đề kỹ thuật bạn đã giải quyết (không bắt buộc)"
              rows={6}
              value={draft.essays.problem_solving}
              onChange={(e) => setDraft(update(draft, "essays", { ...draft.essays, problem_solving: e.target.value }))}
            />
            <fieldset className="stack">
              <legend className="th-field__label">Nguyện vọng nhánh học (chọn tối đa 3, theo thứ tự ưu tiên)</legend>
              <p className="muted">Nguyện vọng chỉ dùng để xếp nhánh sau khi trúng tuyển, không ảnh hưởng điểm hồ sơ.</p>
              {tracks.map((t) => {
                const rank = draft.tracks.indexOf(t.key);
                return (
                  <Checkbox
                    key={t.key}
                    label={rank >= 0 ? `${t.name.vi ?? t.key} (ưu tiên ${rank + 1})` : (t.name.vi ?? t.key)}
                    checked={rank >= 0}
                    disabled={rank < 0 && draft.tracks.length >= 3}
                    onChange={(e) => setDraft(update(draft, "tracks", e.target.checked ? [...draft.tracks, t.key] : draft.tracks.filter((k) => k !== t.key)))}
                  />
                );
              })}
            </fieldset>
          </>
        )}

        {step === "review" && (
          <>
            {missing.length > 0 ? (
              <Alert tone="danger" title="Hồ sơ còn thiếu thông tin">
                <ul className="plain-list">
                  {missing.map(([path, message]) => (
                    <li key={path}>
                      <button type="button" className="link-button" onClick={() => setStep(stepOfField(path))}>
                        {FIELD_LABELS[path] ?? path}
                      </button>
                      : {message}
                    </li>
                  ))}
                </ul>
              </Alert>
            ) : null}
            <dl className="summary">
              <div><dt>Họ tên</dt><dd>{draft.profile.full_name || "—"}</dd></div>
              <div><dt>Điện thoại</dt><dd>{draft.profile.phone || "—"}</dd></div>
              <div><dt>Học vấn</dt><dd>{draft.education.filter((e) => e.school).map((e) => e.school).join("; ") || "—"}</dd></div>
              <div><dt>Dự án</dt><dd>{draft.projects.filter((p) => p.title).length}</dd></div>
              <div><dt>Kỹ năng</dt><dd>{draft.skills || "—"}</dd></div>
              <div><dt>Bài luận</dt><dd>{essayLength} ký tự</dd></div>
            </dl>
            <Alert tone="info" title="Về việc dùng AI trong xét tuyển">
              Hồ sơ có thể được AI hỗ trợ đọc sơ bộ để cán bộ ưu tiên xem kỹ. AI không quyết định kết quả; mọi quyết định do con người đưa ra và được phê duyệt hai cấp.
              Chỉ phần năng lực (không gồm họ tên, giới tính, ngày sinh, nơi ở) được đưa vào AI.
            </Alert>
            {infoOnly ? null : (
              <Checkbox label="Tôi xác nhận thông tin là chính xác và đồng ý để chương trình xử lý dữ liệu cá nhân cho mục đích xét tuyển." checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            )}
            {submitError ? <Alert tone="danger">{submitError}</Alert> : null}
          </>
        )}
      </section>

      <div className="sticky-actions">
        <Button variant="secondary" disabled={stepIndex === 0} onClick={() => setStep(STEPS[stepIndex - 1]!.key)}>
          Quay lại
        </Button>
        {step === "review" ? (
          <Button onClick={() => void submit()} loading={submitting} disabled={!infoOnly && !consent}>
            {infoOnly ? "Lưu và quay lại" : "Nộp hồ sơ"}
          </Button>
        ) : (
          <Button onClick={() => setStep(STEPS[stepIndex + 1]!.key)}>Tiếp tục</Button>
        )}
      </div>
    </div>
  );
}
