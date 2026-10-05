"use client";

import { useSearchParams } from "next/navigation";
import { useFormat, useT } from "@/components/providers";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { SelectField } from "@/components/ui/Fields";
import { DemoNotice, PageHeader, Stat } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import type { Quality } from "@/lib/contracts";
import { useGet } from "@/lib/hooks";
import type { Tone } from "@/lib/labels";
import { useCohortSelection } from "@/lib/use-cohort-selection";
import { qualityMessages } from "./quality-messages";

type Competency = Quality["competencies"][number];

/** Màu theo mức đạt chuẩn: từ 80% xanh, từ 60% vàng, dưới 60% đỏ (khớp ngưỡng "tỉ lệ đạt thấp" của backend). */
function attainmentTone(rate: number | null | undefined, low: number): Tone {
  if (rate == null) return "info";
  if (rate >= 0.8) return "success";
  return rate >= low ? "warning" : "danger";
}

const SEVERITY_TONE: Record<string, Tone> = { danger: "danger", warning: "warning", info: "info" };
const PRIORITY_TONE: Record<string, Tone> = { high: "danger", medium: "warning", low: "info" };

function Meter({ value, tone }: { value: number | null; tone: Tone }) {
  return (
    <span className="meter" data-tone={tone} aria-hidden="true">
      <span className="meter__fill" style={{ width: `${Math.round((value ?? 0) * 100)}%` }} />
    </span>
  );
}

function Trend({ comp }: { comp: Competency }) {
  const m = useT(qualityMessages).outcomes;
  if (comp.previous == null || comp.attainment == null) return <span className="muted">—</span>;
  const pts = Math.round((comp.attainment - comp.previous) * 100);
  if (pts === 0) return <span className="muted">{m.flat}</span>;
  return <Badge tone={pts > 0 ? "success" : pts <= -15 ? "danger" : "warning"}>{pts > 0 ? m.up(String(pts)) : m.down(String(-pts))}</Badge>;
}

function Outcomes({ data }: { data: Quality }) {
  const m = useT(qualityMessages).outcomes;
  const f = useFormat();
  const low = data.thresholds["low_attainment"] ?? 0.6;
  return (
    <section className="th-card panel stack" aria-labelledby="outcomes-title">
      <div>
        <h2 id="outcomes-title" className="th-type-h4">
          {m.heading}
        </h2>
        <p className="muted">{m.help(data.previous_cohort)}</p>
      </div>
      <div className="table-scroll">
        <table className="th-table responsive-table quality-table">
          <thead>
            <tr>
              <th scope="col">{m.competency}</th>
              <th scope="col">{m.attainment}</th>
              <th scope="col">{m.trend}</th>
              <th scope="col">{m.coverage}</th>
              <th scope="col">{m.gap}</th>
              <th scope="col">{m.byTrack}</th>
            </tr>
          </thead>
          <tbody>
            {data.competencies.map((c) => {
              const tone = attainmentTone(c.attainment, low);
              return (
                <tr key={c.id}>
                  <th scope="row" data-label={m.competency}>
                    {c.name}
                  </th>
                  <td data-label={m.attainment}>
                    <span className="quality-rate">
                      <Meter value={c.attainment} tone={tone} />
                      <strong>{f.pct(c.attainment)}</strong>
                      <span className="muted">{m.met(c.met, c.assessed)}</span>
                    </span>
                  </td>
                  <td data-label={m.trend}>
                    <Trend comp={c} />
                  </td>
                  <td data-label={m.coverage}>{f.pct(c.coverage)}</td>
                  <td data-label={m.gap}>{c.avg_gap != null ? m.gapUnit(c.avg_gap.toFixed(1)) : "—"}</td>
                  <td data-label={m.byTrack}>
                    <span className="quality-tracks">
                      {c.by_track.map((b) => (
                        <Badge key={b.track_id} tone={attainmentTone(b.attainment, low)}>
                          {b.track}: {b.attainment != null ? f.pct(b.attainment) : m.noData}
                        </Badge>
                      ))}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Tracks({ data }: { data: Quality }) {
  const m = useT(qualityMessages).tracks;
  const f = useFormat();
  if (data.tracks.length === 0) return null;
  return (
    <section className="th-card panel stack" aria-labelledby="tracks-title">
      <h2 id="tracks-title" className="th-type-h4">
        {m.heading}
      </h2>
      <table className="th-table responsive-table">
        <thead>
          <tr>
            <th scope="col">{m.track}</th>
            <th scope="col">{m.learners}</th>
            <th scope="col">{m.decided}</th>
            <th scope="col">{m.rate}</th>
            <th scope="col">{m.active}</th>
          </tr>
        </thead>
        <tbody>
          {data.tracks.map((t) => (
            <tr key={t.track_id}>
              <th scope="row" data-label={m.track}>
                {t.track}
              </th>
              <td data-label={m.learners}>{f.number(t.learners)}</td>
              <td data-label={m.decided}>
                {f.number(t.qualified)} / {f.number(t.not_qualified)}
              </td>
              <td data-label={m.rate}>{f.pct(t.qualified_rate)}</td>
              <td data-label={m.active}>{f.number(t.active)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Alerts({ data }: { data: Quality }) {
  const m = useT(qualityMessages).alerts;
  return (
    <section className="th-card panel stack" aria-labelledby="alerts-title">
      <h2 id="alerts-title" className="th-type-h4">
        {m.heading}
      </h2>
      {data.alerts.length === 0 ? (
        <Alert tone="success">{m.none}</Alert>
      ) : (
        <ul className="quality-alerts">
          {data.alerts.map((a) => (
            <li key={a.code} className="quality-alert" data-severity={a.severity}>
              <div className="quality-alert__head">
                <Badge tone={SEVERITY_TONE[a.severity] ?? "info"}>{m.severity[a.severity] ?? a.severity}</Badge>
                <strong>{a.title}</strong>
                <span className="muted">{m.count(a.count)}</span>
              </div>
              <p className="muted">{a.detail}</p>
              <details>
                <summary>{m.show(a.items.length, a.count)}</summary>
                <ul className="quality-alert__items">
                  {a.items.map((item) => (
                    <li key={`${item.ref_id}-${item.label}`}>{item.label}</li>
                  ))}
                </ul>
              </details>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Recommendations({ data }: { data: Quality }) {
  const m = useT(qualityMessages).recs;
  return (
    <section className="th-card panel stack" aria-labelledby="recs-title">
      <div>
        <h2 id="recs-title" className="th-type-h4">
          {m.heading}
        </h2>
        <p className="muted">{m.help}</p>
      </div>
      <ol className="quality-recs">
        {data.recommendations.map((r) => (
          <li key={r.title} className="quality-rec">
            <div className="quality-alert__head">
              <Badge tone={PRIORITY_TONE[r.priority] ?? "info"}>{m.priority[r.priority] ?? r.priority}</Badge>
              <strong>{r.title}</strong>
            </div>
            <p>{r.rationale}</p>
            <p className="quality-rec__label">{m.actions}</p>
            <ul>
              {r.actions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Report({ data }: { data: Quality }) {
  const m = useT(qualityMessages);
  const f = useFormat();
  const s = data.summary;
  const th = data.thresholds;
  const danger = data.alerts.filter((a) => a.severity === "danger").length;
  const warning = data.alerts.filter((a) => a.severity === "warning").length;
  return (
    <div className="stack">
      <div className="stat-grid">
        <Stat label={m.stats.learners} value={f.number(s.learners)} hint={m.stats.learnersHint(s.active, s.withdrawn)} />
        <Stat label={m.stats.qualified} value={f.pct(s.qualified_rate)} hint={m.stats.qualifiedHint(s.qualified, s.not_qualified)} />
        <Stat label={m.stats.coverage} value={f.pct(s.coverage)} hint={m.stats.coverageHint} tone={s.coverage == null ? undefined : s.coverage >= 0.95 ? "ok" : "warn"} />
        <Stat label={m.stats.attainment} value={f.pct(s.attainment)} hint={m.stats.attainmentHint} />
        <Stat label={m.stats.alerts} value={f.number(data.alerts.length)} hint={m.stats.alertsHint(danger, warning)} tone={danger > 0 ? "bad" : warning > 0 ? "warn" : "ok"} />
      </div>
      {data.competencies.length > 0 ? <Outcomes data={data} /> : <Alert tone="info">{m.empty}</Alert>}
      <div className="split split--2 quality-split">
        <Alerts data={data} />
        <Recommendations data={data} />
      </div>
      <Tracks data={data} />
      <p className="muted quality-footnote">
        {m.thresholds(f.pct(th["low_attainment"]), th["min_sample"] ?? 20, f.pct(th["drop_points"]), th["assessor_bias"] ?? 0.75, th["level_jump"] ?? 3, th["stale_days"] ?? 60)}
      </p>
    </div>
  );
}

export function QualityView() {
  const m = useT(qualityMessages);
  const params = useSearchParams();
  const { query, cohorts, selected, select } = useCohortSelection();
  // Mặc định: khoá đang học (cần theo dõi nhất), không có thì khoá gần nhất đã kết thúc.
  const cohort = params.get("cohort")
    ? selected
    : (cohorts.find((c) => c.status === "active") ?? cohorts.filter((c) => c.status === "completed").at(-1) ?? selected);
  const quality = useGet<Quality>(cohort ? `/analytics/quality?cohort_id=${cohort.id}` : null);

  return (
    <div className="stack">
      <PageHeader title={m.title} subtitle={m.subtitle} />
      <QueryState query={query} lines={2}>
        {() =>
          !cohort ? (
            <Alert tone="info">{m.noCohort}</Alert>
          ) : (
            <>
              <div className="toolbar quality-toolbar">
                <SelectField label={m.cohort} value={cohort.id} onChange={(e) => select(e.target.value)}>
                  {cohorts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.code})
                    </option>
                  ))}
                </SelectField>
                <a className="th-button th-button--secondary" href={`/api/v1/analytics/quality/report?cohort_id=${cohort.id}`} download>
                  {m.download}
                </a>
              </div>
              <DemoNotice show={cohort.name.startsWith("[Minh hoạ]") || cohort.programName.startsWith("[Minh hoạ]")} />
              <QueryState query={quality} lines={6}>
                {(data) => <Report data={data} />}
              </QueryState>
            </>
          )
        }
      </QueryState>
    </div>
  );
}
