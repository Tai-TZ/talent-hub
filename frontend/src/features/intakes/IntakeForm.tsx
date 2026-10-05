"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Checkbox, SelectField, TextArea } from "@/components/ui/Fields";
import { QueryState } from "@/components/ui/QueryState";
import { TextField } from "@/components/ui/TextField";
import type { IntakeT, ProgramT } from "@/lib/contracts";
import { errorText, useGet, useSend } from "@/lib/hooks";
import { DEFAULT_ROUNDS, ELIGIBILITY_PRESETS, type RoundDraft, ROUND_TYPES, slugify, uniqueKey } from "./templates";

/** `datetime-local` → ISO UTC; giữ giờ địa phương người nhập. */
const toIso = (local: string) => new Date(local).toISOString();
const inDays = (days: number) => {
  const d = new Date(Date.now() + days * 86_400_000);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
};

function Form({ programs, onClose }: { programs: ProgramT[]; onClose: () => void }) {
  const router = useRouter();
  const [programId, setProgramId] = useState(programs[0]?.id ?? "");
  const [cohortId, setCohortId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [opens, setOpens] = useState(inDays(0));
  const [closes, setCloses] = useState(inDays(21));
  const [quota, setQuota] = useState("150");
  const [rounds, setRounds] = useState<RoundDraft[]>(DEFAULT_ROUNDS);
  const [ai, setAi] = useState(false);
  const [blind, setBlind] = useState(true);
  const [minReviews, setMinReviews] = useState("2");
  const [rules, setRules] = useState<string[]>(ELIGIBILITY_PRESETS.map((r) => r.id));
  const [error, setError] = useState<{ message: string; fields: Record<string, string> } | null>(null);
  const create = useSend<IntakeT, Record<string, unknown>>("POST", "/intakes", { invalidate: ["/intakes"] });
  const cohorts = programs.find((p) => p.id === programId)?.cohorts ?? [];

  function setRound(index: number, patch: Partial<RoundDraft>) {
    setRounds((list) => list.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  function submit() {
    setError(null);
    // Khoá vòng sinh từ nhãn, bảo đảm duy nhất.
    const taken: string[] = [];
    const finalRounds = rounds.map((r) => {
      const key = uniqueKey(slugify(r.label, "vong"), taken);
      taken.push(key);
      return { ...r, key };
    });
    create.mutate(
      {
        program_id: programId,
        cohort_id: cohortId || null,
        name: name.trim(),
        description: description.trim(),
        opens_at: toIso(opens),
        closes_at: toIso(closes),
        quota: Number(quota),
        rounds: finalRounds,
        ai_screening_enabled: ai,
        blind_review: blind,
        min_reviews: Number(minReviews),
        eligibility_rules: ELIGIBILITY_PRESETS.filter((r) => rules.includes(r.id)),
      },
      {
        onSuccess: (intake) => {
          onClose();
          router.push(`/intakes/${intake.id}`);
        },
        onError: (e) => setError({ message: errorText(e), fields: e.fields }),
      },
    );
  }

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <TextField label="Tên đợt tuyển" required value={name} maxLength={200} error={error?.fields["name"]} onChange={(e) => setName(e.target.value)} />
      <div className="form-grid">
        <SelectField
          label="Chương trình"
          value={programId}
          onChange={(e) => {
            setProgramId(e.target.value);
            setCohortId("");
          }}
        >
          {programs.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name["vi"] ?? p.code}
            </option>
          ))}
        </SelectField>
        <SelectField label="Khoá học nhận (không bắt buộc)" value={cohortId} onChange={(e) => setCohortId(e.target.value)} help="Người trúng tuyển được ghi danh vào khoá này.">
          <option value="">Chưa chọn</option>
          {cohorts.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </SelectField>
      </div>
      <TextArea label="Mô tả cho ứng viên" rows={3} value={description} maxLength={4000} onChange={(e) => setDescription(e.target.value)} />
      <div className="form-grid">
        <TextField label="Mở nhận hồ sơ" type="datetime-local" required value={opens} onChange={(e) => setOpens(e.target.value)} />
        <TextField label="Đóng nhận hồ sơ" type="datetime-local" required value={closes} error={error?.fields["closes_at"]} onChange={(e) => setCloses(e.target.value)} />
        <TextField label="Chỉ tiêu" type="number" min={1} required value={quota} onChange={(e) => setQuota(e.target.value)} />
        <TextField label="Số người chấm tối thiểu mỗi hồ sơ" type="number" min={1} max={5} value={minReviews} onChange={(e) => setMinReviews(e.target.value)} help="Nên từ 2 để có đối chiếu độc lập." />
      </div>

      <fieldset className="plain-fieldset stack">
        <legend className="th-field__label">Các vòng xét tuyển</legend>
        {rounds.map((r, i) => (
          <div key={i} className="form-grid">
            <TextField label={`Vòng ${i + 1}`} value={r.label} maxLength={80} onChange={(e) => setRound(i, { label: e.target.value })} />
            <SelectField label="Loại" value={r.type} onChange={(e) => setRound(i, { type: e.target.value as RoundDraft["type"] })}>
              {ROUND_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </SelectField>
            <div style={{ alignSelf: "end" }}>
              <Button variant="tertiary" size="sm" disabled={rounds.length === 1} onClick={() => setRounds((list) => list.filter((_, j) => j !== i))}>
                Bỏ vòng
              </Button>
            </div>
          </div>
        ))}
        <div>
          <Button variant="secondary" size="sm" disabled={rounds.length >= 6} onClick={() => setRounds((list) => [...list, { key: "", label: "", type: "review" }])}>
            Thêm vòng
          </Button>
        </div>
      </fieldset>

      <fieldset className="plain-fieldset stack">
        <legend className="th-field__label">Điều kiện sơ bộ (chỉ gắn cờ cho cán bộ, không tự loại hồ sơ)</legend>
        {ELIGIBILITY_PRESETS.map((r) => (
          <Checkbox key={r.id} label={r.label} checked={rules.includes(r.id)} onChange={(e) => setRules((list) => (e.target.checked ? [...list, r.id] : list.filter((x) => x !== r.id)))} />
        ))}
      </fieldset>

      <fieldset className="plain-fieldset stack">
        <legend className="th-field__label">Chính sách xét tuyển</legend>
        <Checkbox label="Chấm mù: ẩn họ tên và liên kết cá nhân với người chấm" checked={blind} onChange={(e) => setBlind(e.target.checked)} />
        <Checkbox label="Dùng AI hỗ trợ sàng lọc sơ bộ (ứng viên được thông báo; AI chỉ gợi ý)" checked={ai} onChange={(e) => setAi(e.target.checked)} />
      </fieldset>

      {error ? <Alert tone="danger">{error.message}</Alert> : null}
      <div className="dialog__actions">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button type="submit" loading={create.isPending} disabled={!name.trim() || !programId || rounds.some((r) => !r.label.trim())}>
          Tạo đợt tuyển nháp
        </Button>
      </div>
      <p className="muted">Sau khi tạo, hãy thiết lập rubric cho từng vòng rồi mở đợt tuyển.</p>
    </form>
  );
}

export function IntakeForm({ onClose }: { onClose: () => void }) {
  const programs = useGet<ProgramT[]>("/programs");
  return (
    <QueryState query={programs} lines={4}>
      {(list) => (list.length === 0 ? <Alert tone="warning">Chưa có chương trình nào. Hãy tạo chương trình trước.</Alert> : <Form programs={list} onClose={onClose} />)}
    </QueryState>
  );
}
