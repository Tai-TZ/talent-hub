"use client";

import { useEffect, useMemo, useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Checkbox, Range } from "@/components/ui/Fields";
import { BarList, DemoNotice, ForestPlot, PageHeader, Stat } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { IntakeT, Lab } from "@/lib/contracts";
import { fmtNumber, fmtPct } from "@/lib/format";
import { errorText, useGet, useSend } from "@/lib/hooks";

type Simulation = NonNullable<Lab["simulation"]>;

const ATTR: Record<string, string> = { gender: "giới tính", region: "khu vực" };

function Fairness({ before, after }: { before: Simulation["fairness_old"]; after: Simulation["fairness_new"] }) {
  const attrs = Object.keys(after);
  if (attrs.length === 0) return null;
  return (
    <ul className="plain-list stack">
      {attrs.map((a) => {
        const o = before[a]?.impact_ratio;
        const n = after[a]?.impact_ratio;
        return (
          <li key={a} className="row-actions">
            <strong>Tỉ lệ tác động theo {ATTR[a] ?? a}:</strong>
            <span>{o != null ? o.toFixed(2) : "—"}</span>
            <span aria-hidden="true">→</span>
            <StatusBadge entry={[n != null ? n.toFixed(2) : "chưa đủ dữ liệu", n != null && n < 0.8 ? "warning" : "success"]} />
          </li>
        );
      })}
    </ul>
  );
}

function SimulationPanel({ sim }: { sim: Simulation }) {
  return (
    <section className="th-card panel stack" aria-labelledby="sim-title">
      <h2 id="sim-title" className="th-type-h4">
        Kết quả mô phỏng với trọng số mới
      </h2>
      <div className="stat-grid">
        <Stat label="Danh sách trùng với rubric cũ" value={fmtPct(sim.overlap_old_new)} hint={`${fmtNumber(sim.changed_in)} người mới vào danh sách`} />
        <Stat label="Tỉ lệ đạt (đã quan sát) – cũ" value={fmtPct(sim.observed_old.qualified_rate, 1)} hint={`${sim.observed_old.known}/${sim.observed_old.of} có kết quả`} />
        <Stat label="Tỉ lệ đạt (đã quan sát) – mới" value={fmtPct(sim.observed_new.qualified_rate, 1)} hint={`${sim.observed_new.known}/${sim.observed_new.of} có kết quả`} />
        {sim.model_expected_new != null ? <Stat label="Kỳ vọng theo mô hình – mới" value={fmtPct(sim.model_expected_new, 1)} hint={`Cũ: ${fmtPct(sim.model_expected_old, 1)}`} /> : null}
      </div>
      <Fairness before={sim.fairness_old} after={sim.fairness_new} />
      <Alert tone="info" title="Cách đọc kết quả">
        Mô phỏng chỉ xếp hạng lại những người đã nộp hồ sơ. Tỉ lệ đạt &quot;đã quan sát&quot; chỉ tính trên người đã được nhận và đã có kết quả; phần kỳ vọng theo mô hình là ngoại suy cho cả người chưa được nhận nên chỉ để tham khảo.
        {sim.model_note ? ` ${sim.model_note}` : ""}
      </Alert>
    </section>
  );
}

function Results({ lab, ids }: { lab: Lab; ids: string[] }) {
  const analysis = lab.analysis;
  const names = useMemo(() => Object.fromEntries(lab.criteria.map((c) => [c.id, c.name])), [lab.criteria]);
  const [weights, setWeights] = useState<Record<string, number>>(lab.old_weights);
  const [error, setError] = useState<string | null>(null);
  const simulate = useSend<Lab, { intake_ids: string[]; weights: Record<string, number> }>("POST", "/analytics/lab");
  const sim = simulate.data?.simulation;

  return (
    <div className="stack">
      <div className="stat-grid">
        <Stat label="Hồ sơ trong mẫu" value={fmtNumber(lab.pool)} />
        <Stat label="Đã được nhận" value={fmtNumber(lab.admitted)} />
        <Stat label="Có kết quả khoá học" value={fmtNumber(analysis.n)} hint={analysis.qualified_rate != null ? `${fmtPct(analysis.qualified_rate)} đạt yêu cầu` : undefined} />
        <Stat label="Khả năng dự báo (AUC kiểm chứng chéo)" value={analysis.model_auc != null ? analysis.model_auc.toFixed(2) : "—"} hint="0,5 = đoán ngẫu nhiên; 1 = hoàn hảo" tone={(analysis.model_auc ?? 0) >= 0.65 ? "ok" : "warn"} />
      </div>

      <Alert tone={analysis.reliable ? "info" : "warning"} title={analysis.reliable ? "Lưu ý khi diễn giải" : "Dữ liệu chưa đủ để kết luận chắc chắn"}>
        <ul className="plain-list">
          {analysis.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      </Alert>

      {analysis.criteria.length > 0 ? (
        <section className="th-card panel stack" aria-labelledby="forest-title">
          <h2 id="forest-title" className="th-type-h4">
            Tiêu chí nào thực sự dự báo kết quả học?
          </h2>
          <p className="muted">
            Hệ số hồi quy logistic trên điểm đã chuẩn hoá; thanh là khoảng tin cậy 90% (bootstrap). Khoảng không chạm 0 (màu đậm) nghĩa là tiêu chí có liên hệ rõ với việc học viên đạt yêu cầu.
          </p>
          <ForestPlot rows={analysis.criteria.map((c) => ({ label: names[c.criterion] ?? c.criterion, value: c.coef, lo: c.ci90[0] ?? 0, hi: c.ci90[1] ?? 0, significant: c.significant }))} />
        </section>
      ) : null}

      <section className="th-card panel stack" aria-labelledby="whatif-title">
        <h2 id="whatif-title" className="th-type-h4">
          Thử đổi trọng số rubric
        </h2>
        <p className="muted">Kéo trọng số rồi chạy mô phỏng: danh sách được chọn thay đổi ra sao, tỉ lệ đạt kỳ vọng và công bằng nhóm có tốt hơn không.</p>
        <div className="form-grid">
          {lab.criteria.map((c) => (
            <Range key={c.id} label={c.name} value={weights[c.id] ?? 0} min={0} max={10} step={0.5} onChange={(v) => setWeights((w) => ({ ...w, [c.id]: v }))} format={(v) => `${v} (hiện tại ${lab.old_weights[c.id] ?? 0})`} />
          ))}
        </div>
        {error ? <Alert tone="danger">{error}</Alert> : null}
        <div className="row-actions">
          <Button
            loading={simulate.isPending}
            onClick={() => {
              setError(null);
              simulate.mutate({ intake_ids: ids, weights }, { onError: (e) => setError(errorText(e)) });
            }}
          >
            Chạy mô phỏng
          </Button>
          <Button variant="tertiary" onClick={() => setWeights(lab.old_weights)}>
            Đặt lại trọng số hiện tại
          </Button>
        </div>
      </section>

      {sim ? <SimulationPanel sim={sim} /> : null}

      <section className="th-card panel stack" aria-labelledby="old-title">
        <h2 id="old-title" className="th-type-h4">
          Trọng số rubric hiện tại
        </h2>
        <BarList rows={lab.criteria.map((c) => ({ label: c.name, value: c.weight }))} />
      </section>
    </div>
  );
}

export function LabView() {
  const intakes = useGet<IntakeT[]>("/intakes");
  const finished = useMemo(() => (intakes.data ?? []).filter((i) => (i.status === "closed" || i.status === "archived") && (i.counts["ACCEPTED"] ?? 0) + (i.counts["ENROLLED"] ?? 0) > 0), [intakes.data]);
  const [picked, setPicked] = useState<string[] | null>(null);
  const ids = picked ?? finished.map((i) => i.id);

  const lab = useSend<Lab, { intake_ids: string[] }>("POST", "/analytics/lab");
  const run = lab.variables?.intake_ids ?? null;
  const { isIdle, mutate } = lab;
  // Tự phân tích khi mở trang lần đầu với các đợt đã kết thúc.
  useEffect(() => {
    if (isIdle && finished.length > 0) mutate({ intake_ids: finished.map((i) => i.id) });
  }, [isIdle, finished, mutate]);

  return (
    <div className="stack">
      <PageHeader title="Rubric Lab" subtitle="Dùng kết quả khoá học của các đợt trước để kiểm tra tiêu chí chấm nào thực sự dự báo thành công, rồi thử đổi trọng số trước khi áp dụng cho đợt sau." />
      <QueryState query={intakes} lines={2}>
        {() =>
          finished.length === 0 ? (
            <Alert tone="info">Chưa có đợt tuyển nào đã đóng và có người được nhận để phân tích. Rubric Lab cần kết quả khoá học của các đợt trước.</Alert>
          ) : (
            <>
              <DemoNotice show={finished.some((i) => i.name.startsWith("[Minh hoạ]"))} />
              <fieldset className="th-card panel plain-fieldset stack">
                <legend className="th-field__label">Các đợt đưa vào phân tích</legend>
                <div className="row-actions">
                  {finished.map((i) => (
                    <Checkbox key={i.id} label={i.name} checked={ids.includes(i.id)} onChange={(e) => setPicked(e.target.checked ? [...ids, i.id] : ids.filter((x) => x !== i.id))} />
                  ))}
                </div>
                <div>
                  <Button
                    variant="secondary"
                    loading={lab.isPending}
                    disabled={ids.length === 0}
                    onClick={() => lab.mutate({ intake_ids: ids })}
                  >
                    Phân tích lại
                  </Button>
                </div>
              </fieldset>
              {lab.isError ? <Alert tone="danger">{errorText(lab.error)}</Alert> : null}
              {lab.isPending && !lab.data ? <p className="muted">Đang phân tích…</p> : null}
              {lab.data && run ? <Results key={run.join(",") + lab.data.pool} lab={lab.data} ids={run} /> : null}
            </>
          )
        }
      </QueryState>
    </div>
  );
}
