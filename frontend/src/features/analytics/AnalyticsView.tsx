"use client";

import { IntakePicker } from "@/components/IntakePicker";
import { useFormat, useLabels, useT } from "@/components/providers";
import { Alert } from "@/components/ui/Alert";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { BarList, DemoNotice, PageHeader, Stat } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import type { Fairness, Funnel, IntakeT } from "@/lib/contracts";
import { useGet } from "@/lib/hooks";
import { useIntakeSelection } from "@/lib/use-intake-selection";
import { messages } from "./messages";

function FunnelPanel({ data }: { data: Funnel }) {
  const m = useT(messages).funnel;
  const f = useFormat();
  const L = useLabels();
  const first = data.stages[0]?.count ?? 0;
  return (
    <div className="stack">
      <div className="stat-grid">
        <Stat label={m.submitted} value={f.number(first)} />
        <Stat label={m.quotaFill} value={f.pct(data.quota_fill)} hint={m.quota(f.number(data.intake.quota))} tone={(data.quota_fill ?? 0) >= 1 ? "ok" : undefined} />
        <Stat label={m.timeToDecision} value={data.median_days_to_decision != null ? m.days(data.median_days_to_decision) : "—"} hint={m.timeToDecisionHint} />
      </div>
      <section className="th-card panel stack" aria-labelledby="funnel-title">
        <h2 id="funnel-title" className="th-type-h4">
          {m.heading}
        </h2>
        <BarList
          rows={data.stages.map((s, i) => {
            const prev = i === 0 ? s.count : (data.stages[i - 1]?.count ?? 0);
            return { label: s.label, value: s.count, hint: i === 0 || prev === 0 ? "" : m.vsPrevious(f.pct(s.count / prev)) };
          })}
          format={f.number}
        />
        <p className="muted">
          {m.decided}{" "}
          {Object.entries(data.decisions).length === 0
            ? m.none
            : Object.entries(data.decisions)
                .map(([k, v]) => `${L.outcome(k)[0]} ${f.number(v)}`)
                .join(" · ")}
        </p>
      </section>
    </div>
  );
}

function FairnessPanel({ data }: { data: Fairness }) {
  const m = useT(messages).fairness;
  const f = useFormat();
  const stages = Object.entries(data.stages);
  return (
    <section className="th-card panel stack" aria-labelledby="fair-title">
      <h2 id="fair-title" className="th-type-h4">
        {m.heading}
      </h2>
      <p className="muted">{data.note}</p>
      {data.warnings.length > 0 ? (
        <Alert tone="warning" title={m.review}>
          <ul className="plain-list">
            {data.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Alert>
      ) : (
        <Alert tone="success">{m.allClear}</Alert>
      )}
      {stages.map(([stage, attrs]) => (
        <div key={stage} className="stack">
          <h3 className="th-type-h5">{stage === "accepted" ? m.accepted : m.reached(stage.replace("reached_", ""))}</h3>
          <div className="split split--2">
            {Object.entries(attrs).map(([attr, g]) => (
              <div key={attr} className="stack">
                <p className="row-actions">
                  <strong>{m.attributes[attr] ?? attr}</strong>
                  {g.impact_ratio != null ? (
                    <StatusBadge entry={[m.impactRatio(g.impact_ratio.toFixed(2)), g.impact_ratio < 0.8 ? "warning" : "success"]} />
                  ) : (
                    <span className="muted">{m.notEnoughData}</span>
                  )}
                </p>
                {Object.values(g.rates).every((r) => r === 0) ? (
                  <p className="muted">{m.nobodyYet}</p>
                ) : (
                  <BarList
                    rows={Object.entries(g.rates).map(([group, rate]) => ({
                      label: m.groups[group] ?? group,
                      value: rate,
                      hint: `n=${f.number(g.sizes[group] ?? 0)}`,
                      tone: "info" as const,
                    }))}
                    format={(v) => f.pct(v, 1)}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
      <p className="muted">{m.footnote}</p>
    </section>
  );
}

const hasOutcomes = (i: IntakeT) => (i.counts["ACCEPTED"] ?? 0) + (i.counts["ENROLLED"] ?? 0) > 0;

export function AnalyticsView() {
  const m = useT(messages).funnel;
  const { query: intakesQuery, intakes, selected, select } = useIntakeSelection(hasOutcomes);
  const id = selected?.id;
  const funnel = useGet<Funnel>(id ? `/analytics/funnel?intake_id=${id}` : null);
  const fairness = useGet<Fairness>(id ? `/analytics/fairness?intake_id=${id}` : null);

  return (
    <div className="stack">
      <PageHeader title={m.title} subtitle={m.subtitle} />
      <QueryState query={intakesQuery} lines={2}>
        {() => (
          <>
            <div className="toolbar">
              <IntakePicker intakes={intakes} selected={selected} onSelect={select} />
            </div>
            <DemoNotice show={Boolean(selected?.name.startsWith("[Minh hoạ]"))} />
            <QueryState query={funnel} lines={5}>
              {(data) => <FunnelPanel data={data} />}
            </QueryState>
            <QueryState query={fairness} lines={5}>
              {(data) => <FairnessPanel data={data} />}
            </QueryState>
          </>
        )}
      </QueryState>
    </div>
  );
}
