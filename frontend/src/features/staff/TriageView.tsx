"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { IntakePicker } from "@/components/IntakePicker";
import { useMe } from "@/components/providers";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Checkbox, SelectField } from "@/components/ui/Fields";
import { DemoNotice, PageHeader, Progress, Stat, StackedHistogram } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Job, TriageBoard } from "@/lib/contracts";
import { fmtNumber, fmtPct, fmtScore, fmtUsd } from "@/lib/format";
import { errorText, useGet, useSend } from "@/lib/hooks";
import { tierLabel } from "@/lib/labels";
import { useIntakeSelection } from "@/lib/use-intake-selection";

const PAGE = 25;
const TIERS = ["invite", "review", "decline_likely"] as const;
const TIER_TONE = { invite: "ok", review: "info", decline_likely: "bad" } as const;
const JOB_KEY = (intakeId: string) => `triage-job:${intakeId}`;

function storedJob(intakeId: string | undefined): string | null {
  if (!intakeId) return null;
  try {
    return sessionStorage.getItem(JOB_KEY(intakeId));
  } catch {
    return null;
  }
}

function rememberJob(intakeId: string, jobId: string | null) {
  try {
    if (jobId) sessionStorage.setItem(JOB_KEY(intakeId), jobId);
    else sessionStorage.removeItem(JOB_KEY(intakeId));
  } catch {
    // Trình duyệt chặn lưu trữ: chỉ mất khả năng nối lại tiến độ sau khi tải lại trang.
  }
}

function JobCard({ job }: { job: Job }) {
  const r = job.result ?? {};
  const total = Math.max(job.total, 1);
  if (job.status === "failed") return <Alert tone="danger" title="Sàng lọc gặp lỗi">{job.error ?? "Không rõ nguyên nhân."}</Alert>;
  if (job.status === "done") {
    return (
      <Alert tone="success" title="Đã sàng lọc xong">
        Chấm {fmtNumber(Number(r["processed"] ?? 0))} hồ sơ trong {String(r["duration_s"] ?? "—")} giây
        {Number(r["failed"] ?? 0) > 0 ? `, ${r["failed"]} hồ sơ lỗi (chưa chấm)` : ""}. Điểm trung bình {fmtScore(r["avg_score"] as number | null)}.
        {Number(r["dropped_quotes"] ?? 0) > 0 ? ` Đã loại ${r["dropped_quotes"]} trích dẫn không kiểm chứng được trong hồ sơ.` : " Mọi trích dẫn bằng chứng đều được kiểm chứng nguyên văn."}
        {Number(r["duplicates_flagged"] ?? 0) > 0 ? ` ${r["duplicates_flagged"]} bài luận trùng lặp bị gắn cờ.` : ""}
        {Number(r["cost_usd"] ?? 0) > 0 ? ` Chi phí AI ${fmtUsd(Number(r["cost_usd"]))}.` : " Chạy offline, không phát sinh chi phí AI."}
      </Alert>
    );
  }
  return (
    <div className="th-card panel stack" role="status" aria-live="polite">
      <strong>{job.status === "queued" ? "Đang xếp hàng…" : `Đang chấm ${fmtNumber(job.done)} / ${fmtNumber(job.total)} hồ sơ`}</strong>
      <Progress value={job.done} max={total} label="Tiến độ sàng lọc" />
    </div>
  );
}

export function TriageView() {
  const me = useMe();
  const { query: intakesQuery, intakes, selected, select } = useIntakeSelection();
  const [round, setRound] = useState("");
  const [tier, setTier] = useState<string>("");
  const [attention, setAttention] = useState(false);
  const [offset, setOffset] = useState(0);
  const [started, setStarted] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const intakeId = selected?.id;
  const roundKey = round || selected?.rounds[0]?.key || "";

  // Nối lại tiến độ nếu người dùng tải lại trang giữa lúc đang chạy (đọc từ sessionStorage).
  const jobId = intakeId ? (started[intakeId] ?? storedJob(intakeId)) : null;

  const params = new URLSearchParams({ round: roundKey, limit: String(PAGE), offset: String(offset) });
  if (tier) params.set("tier", tier);
  if (attention) params.set("attention", "true");
  const board = useGet<TriageBoard>(intakeId && roundKey ? `/intakes/${intakeId}/triage?${params}` : null);
  const job = useGet<Job>(jobId ? `/jobs/${jobId}` : null, {
    refetchInterval: (data) => (!data || data.status === "queued" || data.status === "running" ? 700 : false),
  });

  const start = useSend<{ job_id: string; total: number }, { round: string; force: boolean }>("POST", `/intakes/${intakeId}/triage`);
  const running = job.data?.status === "queued" || job.data?.status === "running";

  // Khi job xong thì làm mới bảng.
  const finished = job.data?.status === "done";
  useEffect(() => {
    if (finished) void board.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finished]);

  function run(force: boolean) {
    if (!intakeId) return;
    setError(null);
    start.mutate(
      { round: roundKey, force },
      {
        onSuccess: (r) => {
          rememberJob(intakeId, r.job_id);
          setStarted((prev) => ({ ...prev, [intakeId]: r.job_id }));
        },
        onError: (e) => setError(errorText(e)),
      },
    );
  }

  const canRun = me.permissions.includes("triage.run");
  const histogram = useMemo(() => {
    const data = board.data;
    if (!data) return null;
    const buckets = Array.from({ length: 10 }, (_, i) => i + 1);
    return {
      buckets,
      series: TIERS.map((t) => ({
        key: t,
        label: tierLabel(t)[0],
        tone: TIER_TONE[t],
        counts: Object.fromEntries(data.histogram.filter((h) => h.tier === t).map((h) => [h.bucket, h.count])) as Record<number, number>,
      })),
    };
  }, [board.data]);

  return (
    <div className="stack">
      <PageHeader
        title="Sàng lọc AI"
        subtitle="AI đọc sơ bộ để cán bộ ưu tiên xem kỹ. Mọi điểm đều kèm bằng chứng trích nguyên văn từ hồ sơ; AI không quyết định kết quả."
      />
      <QueryState query={intakesQuery} lines={2}>
        {() => (
          <>
            <div className="toolbar">
              <IntakePicker
                intakes={intakes}
                selected={selected}
                onSelect={(id) => {
                  select(id);
                  setRound("");
                  setOffset(0);
                }}
              />
              <SelectField
                label="Vòng"
                value={roundKey}
                onChange={(e) => {
                  setRound(e.target.value);
                  setOffset(0);
                }}
              >
                {selected?.rounds.map((r) => (
                  <option key={r.key} value={r.key}>
                    {r.label}
                  </option>
                ))}
              </SelectField>
            </div>

            <DemoNotice show={Boolean(selected?.name.startsWith("[Minh hoạ]"))} />

            {selected && !selected.ai_screening_enabled ? (
              <Alert tone="warning" title="Đợt này chưa bật sàng lọc AI">
                Ứng viên cần được thông báo trước khi dùng AI. Quản trị viên có thể bật trong phần cấu hình đợt tuyển.
              </Alert>
            ) : null}

            {job.data ? <JobCard job={job.data} /> : null}
            {error ? <Alert tone="danger">{error}</Alert> : null}

            {canRun && selected?.ai_screening_enabled ? (
              <div className="row-actions">
                <Button onClick={() => run(false)} loading={start.isPending || running} disabled={!roundKey}>
                  Chạy sàng lọc hồ sơ chưa chấm
                </Button>
                <Button variant="secondary" onClick={() => run(true)} disabled={start.isPending || running || !roundKey}>
                  Chấm lại toàn bộ
                </Button>
              </div>
            ) : null}

            <QueryState query={board} lines={6}>
              {(data) =>
                data.scored === 0 ? (
                  <EmptyState title="Chưa có hồ sơ nào được AI chấm ở vòng này">
                    {data.pool > 0 ? `${fmtNumber(data.pool)} hồ sơ đang chờ trong vòng. Bấm "Chạy sàng lọc" để bắt đầu.` : "Chưa có hồ sơ nào trong vòng này."}
                  </EmptyState>
                ) : (
                  <>
                    <div className="stat-grid">
                      <Stat label="Hồ sơ trong vòng" value={fmtNumber(data.pool)} hint={`${fmtNumber(data.scored)} đã được AI chấm (${fmtPct(data.pool ? data.scored / data.pool : 0)})`} />
                      {TIERS.map((t) => (
                        <Stat
                          key={t}
                          label={tierLabel(t)[0]}
                          value={fmtNumber(data.tiers[t]?.count ?? 0)}
                          hint={`${fmtNumber(data.tiers[t]?.attention ?? 0)} ưu tiên xem kỹ`}
                          tone={t === "invite" ? "ok" : t === "decline_likely" ? "bad" : "warn"}
                        />
                      ))}
                    </div>

                    <section className="th-card panel stack" aria-labelledby="hist-title">
                      <h2 id="hist-title" className="th-type-h4">
                        Phân bố điểm gợi ý
                      </h2>
                      {histogram ? <StackedHistogram buckets={histogram.buckets} series={histogram.series} labelOf={(b) => `${(b - 1) * 10}–${b * 10}`} /> : null}
                      <p className="muted">
                        Ngưỡng hiện tại: nên mời từ {data.thresholds["invite"]} điểm, khả năng loại dưới {data.thresholds["decline"]} điểm; hồ sơ có độ tin cậy thấp hoặc có cờ luôn được đánh dấu &quot;ưu tiên xem kỹ&quot;. Nhóm &quot;khả năng
                        loại&quot; không bao giờ bị loại tự động.
                      </p>
                    </section>

                    <section className="stack" aria-labelledby="list-title">
                      <h2 id="list-title" className="th-type-h4">
                        Hồ sơ theo điểm AI (cao đến thấp)
                      </h2>
                      <div className="row-actions" role="group" aria-label="Lọc theo nhóm gợi ý">
                        {[{ key: "", label: "Tất cả", count: data.scored }, ...TIERS.map((t) => ({ key: t, label: tierLabel(t)[0], count: data.tiers[t]?.count ?? 0 }))].map((t) => (
                          <button
                            key={t.key}
                            type="button"
                            className="chip"
                            aria-pressed={tier === t.key}
                            onClick={() => {
                              setTier(t.key);
                              setOffset(0);
                            }}
                          >
                            {t.label} <span className="chip__count">{fmtNumber(t.count)}</span>
                          </button>
                        ))}
                        <Checkbox
                          label="Chỉ hồ sơ ưu tiên xem kỹ"
                          checked={attention}
                          onChange={(e) => {
                            setAttention(e.target.checked);
                            setOffset(0);
                          }}
                        />
                      </div>

                      {data.items.length === 0 ? (
                        <EmptyState title="Không có hồ sơ phù hợp bộ lọc" />
                      ) : (
                        <div className="table-wrap">
                          <table className="th-table responsive-table">
                            <thead>
                              <tr>
                                <th scope="col">Mã hồ sơ</th>
                                <th scope="col">Họ tên</th>
                                <th scope="col">Điểm AI</th>
                                <th scope="col">Nhóm gợi ý</th>
                                <th scope="col">Độ tin cậy</th>
                                <th scope="col">Cờ</th>
                              </tr>
                            </thead>
                            <tbody>
                              {data.items.map((item) => (
                                <tr key={item.application_id}>
                                  <td data-label="Mã hồ sơ">
                                    <Link href={`/staff/applications/${item.application_id}`} className="mono">
                                      {item.candidate_code}
                                    </Link>
                                  </td>
                                  <td data-label="Họ tên">{item.name ?? <span className="muted">Ẩn danh</span>}</td>
                                  <td data-label="Điểm AI">
                                    <span className="score-chip">{fmtScore(item.total_score)}</span>
                                  </td>
                                  <td data-label="Nhóm gợi ý">
                                    <span className="row-actions">
                                      <StatusBadge entry={tierLabel(item.tier)} />
                                      {item.needs_attention ? <StatusBadge entry={["Ưu tiên xem kỹ", "warning"]} /> : null}
                                    </span>
                                  </td>
                                  <td data-label="Độ tin cậy">{fmtPct(item.confidence)}</td>
                                  <td data-label="Cờ">{item.flag_count > 0 ? item.flag_count : "—"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      <nav className="pager" aria-label="Phân trang danh sách triage">
                        <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                          ‹ Trước
                        </Button>
                        <span aria-live="polite">
                          {fmtNumber(offset + 1)}–{fmtNumber(offset + data.items.length)}
                        </span>
                        <Button variant="secondary" size="sm" disabled={data.items.length < PAGE} onClick={() => setOffset(offset + PAGE)}>
                          Sau ›
                        </Button>
                      </nav>
                    </section>
                  </>
                )
              }
            </QueryState>
          </>
        )}
      </QueryState>
    </div>
  );
}

