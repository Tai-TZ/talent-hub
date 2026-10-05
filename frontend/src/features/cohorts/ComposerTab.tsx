"use client";

import { useState } from "react";
import { useMe } from "@/components/providers";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Range } from "@/components/ui/Fields";
import { BarList, Stat } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { TextField } from "@/components/ui/TextField";
import type { CohortOverview, ComposerRun, ComposerRunDetail } from "@/lib/contracts";
import { fmtDateTime, fmtNumber, fmtPct } from "@/lib/format";
import { errorText, useGet, useSend } from "@/lib/hooks";

type Mode = "levels" | "balanced";

const MODES: { value: Mode; title: string; text: string }[] = [
  { value: "levels", title: "Theo mức", text: "Học viên cùng trình độ học cùng lớp: dễ dạy đúng tốc độ." },
  { value: "balanced", title: "Cân bằng", text: "Mỗi lớp có đủ mọi trình độ và nền tảng: học viên kèm cặp lẫn nhau." },
];

function RunMetrics({ run, trackNames }: { run: ComposerRun; trackNames: Record<string, string> }) {
  const m = run.metrics;
  return (
    <div className="stack">
      <div className="stat-grid">
        <Stat label="Đúng nguyện vọng 1" value={fmtPct(m.pref_first_rate)} tone={(m.pref_first_rate ?? 0) >= 0.6 ? "ok" : "warn"} />
        <Stat label="Trong 2 nguyện vọng đầu" value={fmtPct(m.pref_top2_rate)} />
        <Stat label="Độ phù hợp trung bình" value={fmtPct(m.avg_fit)} />
        <Stat label="Chênh điểm TB giữa các lớp" value={m.class_mean_spread.toFixed(1)} hint="Thấp = các lớp đồng đều" />
        {m.placement_rate != null ? <Stat label="Có nơi thực chiến" value={fmtPct(m.placement_rate)} hint={`${fmtNumber(m.placed)} học viên`} /> : null}
      </div>

      <div className="stack">
        <section className="th-card panel stack" aria-labelledby="mc-class">
          <h3 id="mc-class" className="th-type-h4">
            Các lớp
          </h3>
          <div className="table-wrap table-wrap--scroll">
            <table className="th-table">
              <thead>
                <tr>
                  <th scope="col">Lớp</th>
                  <th scope="col">Sĩ số</th>
                  <th scope="col">Điểm TB</th>
                  <th scope="col">Độ lệch</th>
                  <th scope="col">Khoảng điểm</th>
                  <th scope="col">Nền tảng</th>
                </tr>
              </thead>
              <tbody>
                {m.classes.map((c) => (
                  <tr key={c.index}>
                    <td>
                      <strong>{run.params["class_mode"] === "levels" ? `Mức ${c.index + 1}` : `Lớp ${c.index + 1}`}</strong>
                    </td>
                    <td>{c.size}</td>
                    <td>{c.mean_score}</td>
                    <td>{c.std_score}</td>
                    <td>
                      {c.min_score}–{c.max_score}
                    </td>
                    <td>
                      {Object.entries(c.background)
                        .map(([k, v]) => `${k === "tech" ? "Công nghệ" : "Khác"} ${v}`)
                        .join(" · ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="th-card panel stack" aria-labelledby="mc-track">
          <h3 id="mc-track" className="th-type-h4">
            Lấp đầy nhánh
          </h3>
          <BarList
            rows={Object.entries(m.track_fill).map(([key, f]) => ({
              label: trackNames[key] ?? key,
              value: f.assigned,
              hint: `/ ${f.capacity}`,
              tone: f.assigned >= f.capacity ? "warn" : "info",
            }))}
          />
        </section>
      </div>
    </div>
  );
}

function Assignments({ runId, trackNames }: { runId: string; trackNames: Record<string, string> }) {
  const detail = useGet<ComposerRunDetail>(`/composer/runs/${runId}`);
  return (
    <QueryState query={detail} lines={4}>
      {(d) => (
        <div className="table-wrap">
          <table className="th-table responsive-table">
            <thead>
              <tr>
                <th scope="col">Học viên</th>
                <th scope="col">Lớp</th>
                <th scope="col">Nhánh</th>
                <th scope="col">Vì sao xếp như vậy</th>
              </tr>
            </thead>
            <tbody>
              {d.assignments.slice(0, 200).map((a) => (
                <tr key={a.learner_id}>
                  <td data-label="Học viên">{a.name ?? "—"}</td>
                  <td data-label="Lớp">{a.class_index + 1}</td>
                  <td data-label="Nhánh">{a.track ? (trackNames[a.track] ?? a.track) : "—"}</td>
                  <td data-label="Lý do">{a.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {d.assignments.length > 200 ? <p className="table-footer muted">Hiển thị 200 / {d.assignments.length} học viên đầu tiên.</p> : null}
        </div>
      )}
    </QueryState>
  );
}

export function ComposerTab({ cohortId }: { cohortId: string }) {
  const me = useMe();
  const canManage = me.permissions.includes("cohort.manage");
  const overview = useGet<CohortOverview>(`/cohorts/${cohortId}/overview`);
  const runs = useGet<ComposerRun[]>(`/cohorts/${cohortId}/composer/runs`);

  const [classCount, setClassCount] = useState(3);
  const [mode, setMode] = useState<Mode>("levels");
  const [prefWeight, setPrefWeight] = useState(0.6);
  const [caps, setCaps] = useState<Record<string, string>>({});
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const run = useSend<ComposerRun, Record<string, unknown>>("POST", `/cohorts/${cohortId}/composer/runs`, { invalidate: [`/cohorts/${cohortId}/composer`] });
  const apply = useSend<{ applied: number; skipped: number }, void>("POST", `/composer/runs/${selectedRun}/apply`, { invalidate: ["/cohorts", "/composer"] });

  const tracks = overview.data?.tracks ?? [];
  const trackNames = Object.fromEntries(tracks.map((t) => [t.key, t.name["vi"] ?? t.key]));
  const capOf = (key: string, fallback: number | null) => (caps[key] !== undefined ? caps[key] : fallback != null ? String(fallback) : "");
  const totalCap = tracks.reduce((sum, t) => sum + (Number(capOf(t.key, t.capacity)) || 0), 0);
  const active = overview.data?.enrollments["active"] ?? 0;
  const history = runs.data ?? [];
  const current = history.find((r) => r.id === selectedRun) ?? history[0];

  function start() {
    setMessage(null);
    const track_capacity: Record<string, number> = {};
    for (const t of tracks) {
      const v = Number(capOf(t.key, t.capacity));
      if (v > 0) track_capacity[t.key] = v;
    }
    run.mutate(
      { class_count: classCount, class_mode: mode, pref_weight: prefWeight, fit_weight: Math.round((1 - prefWeight) * 100) / 100, track_capacity },
      {
        onSuccess: (r) => {
          setSelectedRun(r.id);
          setShowDetail(false);
        },
        onError: (e) => setMessage({ tone: "danger", text: errorText(e) }),
      },
    );
  }

  return (
    <div className="stack">
      <p className="muted">
        Composer đề xuất cách xếp nhánh, lớp và nơi thực chiến cho học viên đang học bằng bài toán tối ưu (gán tối ưu toàn cục). Phương án chỉ được áp dụng khi bạn xác nhận; mỗi lượt chạy được lưu để so sánh.
      </p>

      <div className="split split--params">
        <section className="th-card panel stack" aria-labelledby="mc-params">
          <h2 id="mc-params" className="th-type-h4">
            Tham số
          </h2>
          <Range label="Số lớp" value={classCount} min={1} max={10} step={1} onChange={setClassCount} format={(v) => `${v} lớp`} />
          <fieldset className="plain-fieldset stack">
            <legend className="th-field__label">Cách xếp lớp</legend>
            {MODES.map((m) => (
              <label key={m.value} className="choice-card">
                <input type="radio" name="class-mode" checked={mode === m.value} onChange={() => setMode(m.value)} />
                <span>
                  <strong>{m.title}</strong>
                  <span className="muted">{m.text}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <Range
            label="Ưu tiên nguyện vọng so với độ phù hợp"
            value={prefWeight}
            min={0}
            max={1}
            step={0.05}
            onChange={setPrefWeight}
            format={(v) => `${Math.round(v * 100)}% nguyện vọng · ${Math.round((1 - v) * 100)}% phù hợp`}
            help="Độ phù hợp tính từ kỹ năng và dự án trong hồ sơ so với từ khoá của nhánh."
          />
          <fieldset className="plain-fieldset stack">
            <legend className="th-field__label">Sức chứa từng nhánh</legend>
            {tracks.map((t) => (
              <TextField key={t.key} label={t.name["vi"] ?? t.key} type="number" min={0} value={capOf(t.key, t.capacity)} onChange={(e) => setCaps((c) => ({ ...c, [t.key]: e.target.value }))} />
            ))}
            {totalCap < active ? <Alert tone="warning">Tổng sức chứa ({totalCap}) nhỏ hơn số học viên đang học ({active}); Composer sẽ không xếp được hết.</Alert> : null}
          </fieldset>
          {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
          {canManage ? (
            <Button onClick={start} loading={run.isPending} disabled={active === 0}>
              Chạy Composer
            </Button>
          ) : (
            <p className="muted">Bạn chỉ có quyền xem phương án.</p>
          )}
          {active === 0 ? <p className="muted">Khoá chưa có học viên đang học. Hãy ghi danh hồ sơ đã nhận trước.</p> : null}
        </section>

        <section className="stack" aria-label="Kết quả">
          <QueryState query={runs} lines={3}>
            {() =>
              !current ? (
                <Alert tone="info">Chưa có phương án nào. Chọn tham số và bấm &quot;Chạy Composer&quot;.</Alert>
              ) : (
                <>
                  <div className="row-actions">
                    <h2 className="th-type-h4">Phương án lúc {fmtDateTime(current.created_at)}</h2>
                    {current.applied_at ? <Badge tone="success">Đã áp dụng</Badge> : <Badge tone="warning">Chưa áp dụng</Badge>}
                  </div>
                  <RunMetrics run={current} trackNames={trackNames} />
                  <div className="row-actions">
                    <Button variant="secondary" onClick={() => setShowDetail((v) => !v)} aria-expanded={showDetail}>
                      {showDetail ? "Ẩn chi tiết từng học viên" : "Xem chi tiết từng học viên"}
                    </Button>
                    {canManage && !current.applied_at ? (
                      <Button
                        onClick={() => {
                          setSelectedRun(current.id);
                          setConfirm(true);
                        }}
                      >
                        Áp dụng phương án này
                      </Button>
                    ) : null}
                  </div>
                  {showDetail ? <Assignments runId={current.id} trackNames={trackNames} /> : null}
                  {message && message.tone === "success" ? <Alert tone="success">{message.text}</Alert> : null}

                  {history.length > 1 ? (
                    <section className="th-card panel stack" aria-labelledby="mc-history">
                      <h3 id="mc-history" className="th-type-h4">
                        Các lượt chạy trước
                      </h3>
                      <ul className="plain-list stack">
                        {history.map((r) => (
                          <li key={r.id} className="row-actions">
                            <button type="button" className="link-button" aria-current={r.id === current.id} onClick={() => {
                                setSelectedRun(r.id);
                                setShowDetail(false);
                              }}>
                              {fmtDateTime(r.created_at)}
                            </button>
                            <span className="muted">
                              {String(r.params["class_count"])} lớp · {r.params["class_mode"] === "levels" ? "theo mức" : "cân bằng"} · đúng NV1 {fmtPct(r.metrics.pref_first_rate)}
                            </span>
                            {r.applied_at ? <Badge tone="success">Đã áp dụng</Badge> : null}
                          </li>
                        ))}
                      </ul>
                    </section>
                  ) : null}
                </>
              )
            }
          </QueryState>
        </section>
      </div>

      <Dialog open={confirm} title="Áp dụng phương án" size="sm" onClose={() => setConfirm(false)}>
        <div className="stack">
          <p>
            Hệ thống sẽ tạo các lớp còn thiếu và gán nhánh/lớp cho {fmtNumber(current?.metrics.learners ?? 0)} học viên theo phương án này. Học viên đã rút hoặc đã xét kết quả sẽ được bỏ qua. Thao tác được ghi vào nhật ký và không có nút hoàn tác tự động.
          </p>
          <div className="dialog__actions">
            <Button variant="secondary" onClick={() => setConfirm(false)}>
              Huỷ
            </Button>
            <Button
              loading={apply.isPending}
              onClick={() =>
                apply.mutate(undefined, {
                  onSuccess: (r) => {
                    setConfirm(false);
                    setMessage({ tone: "success", text: `Đã áp dụng cho ${fmtNumber(r.applied)} học viên${r.skipped ? `, bỏ qua ${fmtNumber(r.skipped)} học viên đã thay đổi trạng thái` : ""}.` });
                  },
                  onError: (e) => {
                    setConfirm(false);
                    setMessage({ tone: "danger", text: errorText(e) });
                  },
                })
              }
            >
              Xác nhận áp dụng
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
