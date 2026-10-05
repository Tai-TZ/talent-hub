"use client";

import Link from "next/link";
import type { UseMutationResult } from "@tanstack/react-query";
import { useState } from "react";
import { useMe } from "@/components/providers";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Checkbox, TextArea } from "@/components/ui/Fields";
import { PageHeader, Stat, Tabs } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { TextField } from "@/components/ui/TextField";
import type { ApiError } from "@/lib/api";
import type { IntakeT, Rubric } from "@/lib/contracts";
import { fmtDate, fmtNumber } from "@/lib/format";
import { errorText, useGet, useSend } from "@/lib/hooks";
import { applicationStatus, intakeStatus } from "@/lib/labels";
import { RubricEditor } from "./RubricEditor";

const toLocal = (iso: string) => {
  const d = new Date(iso);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
};

function SettingsForm({ intake }: { intake: IntakeT }) {
  const [name, setName] = useState(intake.name);
  const [description, setDescription] = useState(intake.description);
  const [closes, setClosesAt] = useState(toLocal(intake.closes_at));
  const [quota, setQuota] = useState(String(intake.quota));
  const [minReviews, setMinReviews] = useState(String(intake.min_reviews));
  const [ai, setAi] = useState(intake.ai_screening_enabled);
  const [blind, setBlind] = useState(intake.blind_review);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const save = useSend<unknown, Record<string, unknown>>("PATCH", `/intakes/${intake.id}`, { invalidate: ["/intakes"] });
  const locked = intake.status === "closed" || intake.status === "archived";

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        setMessage(null);
        save.mutate(
          { name: name.trim(), description: description.trim(), closes_at: new Date(closes).toISOString(), quota: Number(quota), min_reviews: Number(minReviews), ai_screening_enabled: ai, blind_review: blind },
          { onSuccess: () => setMessage({ tone: "success", text: "Đã lưu thay đổi." }), onError: (err) => setMessage({ tone: "danger", text: errorText(err) }) },
        );
      }}
    >
      {locked ? <Alert tone="info">Đợt tuyển đã đóng nên không thể sửa cấu hình.</Alert> : null}
      <fieldset className="plain-fieldset stack" disabled={locked}>
        <TextField label="Tên đợt tuyển" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
        <TextArea label="Mô tả cho ứng viên" rows={3} value={description} maxLength={4000} onChange={(e) => setDescription(e.target.value)} />
        <div className="form-grid">
          <TextField label="Đóng nhận hồ sơ" type="datetime-local" value={closes} onChange={(e) => setClosesAt(e.target.value)} />
          <TextField label="Chỉ tiêu" type="number" min={1} value={quota} onChange={(e) => setQuota(e.target.value)} />
          <TextField label="Số người chấm tối thiểu" type="number" min={1} max={5} value={minReviews} onChange={(e) => setMinReviews(e.target.value)} />
        </div>
        <Checkbox label="Chấm mù: ẩn họ tên và liên kết cá nhân với người chấm" checked={blind} onChange={(e) => setBlind(e.target.checked)} />
        <Checkbox label="Dùng AI hỗ trợ sàng lọc sơ bộ (ứng viên được thông báo; AI chỉ gợi ý)" checked={ai} onChange={(e) => setAi(e.target.checked)} />
      </fieldset>
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
      {locked ? null : (
        <div>
          <Button type="submit" loading={save.isPending}>
            Lưu thay đổi
          </Button>
        </div>
      )}
    </form>
  );
}

export function IntakeDetail({ id }: { id: string }) {
  const me = useMe();
  const intake = useGet<IntakeT>(`/intakes/${id}`);
  const rubrics = useGet<Record<string, Rubric>>(`/intakes/${id}/rubrics`);
  const [message, setMessage] = useState<{ tone: "success" | "danger" | "info"; text: string } | null>(null);
  const refresh = ["/intakes", "/staff/applications"];
  const publish = useSend<unknown>("POST", `/intakes/${id}/publish`, { invalidate: refresh });
  const close = useSend<unknown>("POST", `/intakes/${id}/close`, { invalidate: refresh });
  const start = useSend<{ moved: number }>("POST", `/intakes/${id}/start`, { invalidate: refresh });
  const canAssign = me.permissions.includes("application.assign");

  return (
    <div className="stack">
      <p>
        <Link href="/intakes">← Đợt tuyển</Link>
      </p>
      <QueryState query={intake} lines={6}>
        {(i) => {
          const submitted = Object.entries(i.counts)
            .filter(([s]) => s !== "DRAFT")
            .reduce((sum, [, n]) => sum + n, 0);
          const missing = i.rounds.filter((r) => !rubrics.data?.[r.key]);
          function run<T>(m: UseMutationResult<T, ApiError, void>, ok: (result: T) => string) {
            setMessage(null);
            m.mutate(undefined, { onSuccess: (r) => setMessage({ tone: "success", text: ok(r) }), onError: (e) => setMessage({ tone: "danger", text: errorText(e) }) });
          }
          return (
            <>
              <PageHeader
                title={i.name}
                subtitle={
                  <>
                    {fmtDate(i.opens_at)} – {fmtDate(i.closes_at)} · {i.rounds.map((r) => r.label).join(" → ")}
                  </>
                }
                actions={
                  <>
                    <StatusBadge entry={intakeStatus(i.status)} />
                    {i.status === "draft" ? (
                      <Button onClick={() => run(publish, () => "Đã mở đợt tuyển. Ứng viên có thể nộp hồ sơ.")} loading={publish.isPending} disabled={missing.length > 0}>
                        Mở đợt tuyển
                      </Button>
                    ) : null}
                    {i.status === "open" ? (
                      <Button variant="secondary" onClick={() => run(close, () => "Đã đóng nhận hồ sơ.")} loading={close.isPending}>
                        Đóng nhận hồ sơ
                      </Button>
                    ) : null}
                    {i.status === "closed" && canAssign && (i.counts["SUBMITTED"] ?? 0) > 0 ? (
                      <Button onClick={() => run(start, (r) => `Đã chuyển ${fmtNumber(r.moved)} hồ sơ vào vòng đầu.`)} loading={start.isPending}>
                        Bắt đầu vòng đầu
                      </Button>
                    ) : null}
                  </>
                }
              />
              {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
              {i.status === "draft" && missing.length > 0 ? <Alert tone="warning">Cần thiết lập rubric cho: {missing.map((r) => r.label).join(", ")} trước khi mở đợt tuyển.</Alert> : null}

              <div className="stat-grid">
                <Stat label="Hồ sơ đã nộp" value={fmtNumber(submitted)} />
                <Stat label="Chỉ tiêu" value={fmtNumber(i.quota)} />
                <Stat label="Được nhận" value={fmtNumber((i.counts["ACCEPTED"] ?? 0) + (i.counts["ENROLLED"] ?? 0))} tone="ok" />
                <Stat label="AI sàng lọc" value={i.ai_screening_enabled ? "Bật" : "Tắt"} hint={i.blind_review ? "Chấm mù" : "Không chấm mù"} />
              </div>
              {Object.keys(i.counts).length > 0 ? (
                <p className="muted">
                  {Object.entries(i.counts)
                    .map(([s, n]) => `${applicationStatus(s)[0]}: ${fmtNumber(n)}`)
                    .join(" · ")}
                </p>
              ) : null}

              <Tabs
                items={[
                  {
                    id: "rubric",
                    label: "Rubric từng vòng",
                    badge: missing.length > 0 ? `thiếu ${missing.length}` : undefined,
                    content: (
                      <QueryState query={rubrics} lines={4}>
                        {(map) => (
                          <div className="stack">
                            {i.rounds.map((r) => (
                              <section key={r.key} className="th-card panel stack" aria-label={`Rubric ${r.label}`}>
                                <h2 className="th-type-h4">
                                  {r.label}
                                  {map[r.key] ? <span className="muted"> · phiên bản {map[r.key]?.version}</span> : null}
                                </h2>
                                <RubricEditor key={r.key} intakeId={i.id} round={r.key} rubric={map[r.key]} locked={false} />
                              </section>
                            ))}
                          </div>
                        )}
                      </QueryState>
                    ),
                  },
                  { id: "settings", label: "Cấu hình", content: <SettingsForm key={i.id + i.status} intake={i} /> },
                ]}
              />
            </>
          );
        }}
      </QueryState>
    </div>
  );
}
