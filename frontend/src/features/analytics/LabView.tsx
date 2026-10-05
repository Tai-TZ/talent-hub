"use client";

import { useEffect, useMemo, useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Range } from "@/components/ui/Fields";
import { CheckIcon } from "@/components/icons";
import { BarList, DemoNotice, ForestPlot, PageHeader, Stat } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Lab, LabIntake } from "@/lib/contracts";
import { useGet, useSend } from "@/lib/hooks";
import { useErrorText, useFormat, useT } from "@/components/providers";
import { messages } from "./messages";
import { commonCriteria, defaultSelection, groupByCriteria, MAX_LAB_INTAKES, type CriteriaGroup } from "./lab-selection";

type Simulation = NonNullable<Lab["simulation"]>;

function Fairness({ before, after }: { before: Simulation["fairness_old"]; after: Simulation["fairness_new"] }) {
  const m = useT(messages).lab.sim;
  const attrs = Object.keys(after);
  if (attrs.length === 0) return null;
  return (
    <ul className="plain-list stack">
      {attrs.map((a) => {
        const o = before[a]?.impact_ratio;
        const n = after[a]?.impact_ratio;
        return (
          <li key={a} className="row-actions">
            <strong>{m.impactBy(m.attributes[a] ?? a)}</strong>
            <span>{o != null ? o.toFixed(2) : "—"}</span>
            <span aria-hidden="true">→</span>
            <StatusBadge entry={[n != null ? n.toFixed(2) : m.notEnough, n != null && n < 0.8 ? "warning" : "success"]} />
          </li>
        );
      })}
    </ul>
  );
}

function SimulationPanel({ sim }: { sim: Simulation }) {
  const m = useT(messages).lab.sim;
  const f = useFormat();
  return (
    <section className="th-card panel stack" aria-labelledby="sim-title">
      <h2 id="sim-title" className="th-type-h4">
        {m.heading}
      </h2>
      <div className="stat-grid">
        <Stat label={m.overlap} value={f.pct(sim.overlap_old_new)} hint={m.newcomers(f.number(sim.changed_in))} />
        <Stat label={m.observedOld} value={f.pct(sim.observed_old.qualified_rate, 1)} hint={m.known(sim.observed_old.known, sim.observed_old.of)} />
        <Stat label={m.observedNew} value={f.pct(sim.observed_new.qualified_rate, 1)} hint={m.known(sim.observed_new.known, sim.observed_new.of)} />
        {sim.model_expected_new != null ? <Stat label={m.modelNew} value={f.pct(sim.model_expected_new, 1)} hint={m.modelOld(f.pct(sim.model_expected_old, 1))} /> : null}
      </div>
      <Fairness before={sim.fairness_old} after={sim.fairness_new} />
      <Alert tone="info" title={m.howToRead}>
        {m.howToReadBody}
        {sim.model_note ? ` ${sim.model_note}` : ""}
      </Alert>
    </section>
  );
}

function Results({ lab, ids }: { lab: Lab; ids: string[] }) {
  const m = useT(messages).lab;
  const f = useFormat();
  const errorText = useErrorText();
  const analysis = lab.analysis;
  const names = useMemo(() => Object.fromEntries(lab.criteria.map((c) => [c.id, c.name])), [lab.criteria]);
  const [weights, setWeights] = useState<Record<string, number>>(lab.old_weights);
  const [error, setError] = useState<string | null>(null);
  const simulate = useSend<Lab, { intake_ids: string[]; weights: Record<string, number> }>("POST", "/analytics/lab");
  const sim = simulate.data?.simulation;

  return (
    <div className="stack">
      <div className="stat-grid">
        <Stat label={m.stats.pool} value={f.number(lab.pool)} />
        <Stat label={m.stats.admitted} value={f.number(lab.admitted)} />
        <Stat label={m.stats.withOutcome} value={f.number(analysis.n)} hint={analysis.qualified_rate != null ? m.stats.qualifiedRate(f.pct(analysis.qualified_rate)) : undefined} />
        <Stat label={m.stats.auc} value={analysis.model_auc != null ? analysis.model_auc.toFixed(2) : "—"} hint={m.stats.aucHint} tone={(analysis.model_auc ?? 0) >= 0.65 ? "ok" : "warn"} />
      </div>

      <Alert tone={analysis.reliable ? "info" : "warning"} title={analysis.reliable ? m.notesTitle : m.unreliableTitle}>
        <ul className="plain-list">
          {analysis.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      </Alert>

      {analysis.criteria.length > 0 ? (
        <section className="th-card panel stack" aria-labelledby="forest-title">
          <h2 id="forest-title" className="th-type-h4">
            {m.forest.heading}
          </h2>
          <p className="muted">{m.forest.help}</p>
          <ForestPlot rows={analysis.criteria.map((c) => ({ label: names[c.criterion] ?? c.criterion, value: c.coef, lo: c.ci90[0] ?? 0, hi: c.ci90[1] ?? 0, significant: c.significant }))} />
        </section>
      ) : null}

      <section className="th-card panel stack" aria-labelledby="whatif-title">
        <h2 id="whatif-title" className="th-type-h4">
          {m.whatIf.heading}
        </h2>
        <p className="muted">{m.whatIf.help}</p>
        <div className="form-grid">
          {lab.criteria.map((c) => (
            <Range key={c.id} label={c.name} value={weights[c.id] ?? 0} min={0} max={10} step={0.5} onChange={(v) => setWeights((w) => ({ ...w, [c.id]: v }))} format={(v) => m.whatIf.current(v, lab.old_weights[c.id] ?? 0)} />
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
            {m.whatIf.run}
          </Button>
          <Button variant="tertiary" onClick={() => setWeights(lab.old_weights)}>
            {m.whatIf.reset}
          </Button>
        </div>
      </section>

      {sim ? <SimulationPanel sim={sim} /> : null}

      <section className="th-card panel stack" aria-labelledby="old-title">
        <h2 id="old-title" className="th-type-h4">
          {m.currentWeights}
        </h2>
        <BarList rows={lab.criteria.map((c) => ({ label: c.name, value: c.weight }))} />
      </section>
    </div>
  );
}

const GROUP_TAG = "ABCDEFGHIJ";

function IntakePicker({
  intakes,
  groups,
  selected,
  onChange,
  onRun,
  running,
}: {
  intakes: LabIntake[];
  groups: CriteriaGroup[];
  selected: string[];
  onChange: (ids: string[]) => void;
  onRun: () => void;
  running: boolean;
}) {
  const m = useT(messages).lab.picker;
  const f = useFormat();
  const common = commonCriteria(intakes, selected);
  const full = selected.length >= MAX_LAB_INTAKES;
  const outcomes = intakes.filter((i) => selected.includes(i.id)).reduce((sum, i) => sum + i.with_outcome, 0);
  const toggle = (id: string, on: boolean) => onChange(on ? [...selected, id] : selected.filter((x) => x !== id));
  // Nhóm có học viên đã có kết quả mới dùng được để đánh giá tiêu chí; nhóm còn lại thu gọn bên dưới.
  const active = groups.filter((g) => g.withOutcome > 0);
  const idle = groups.filter((g) => g.withOutcome === 0);
  const tag = (group: CriteriaGroup) => GROUP_TAG[groups.indexOf(group)] ?? String(groups.indexOf(group) + 1);
  const names = (group: CriteriaGroup) => group.criteria.map((c) => c.name).join(" · ");

  function renderGroup(group: CriteriaGroup) {
    const index = groups.indexOf(group);
    const ids = group.intakes.map((i) => i.id);
    const allIn = ids.every((id) => selected.includes(id));
    const twin = groups.find((g) => g !== group && names(g) === names(group));
    const titleId = `lab-group-${index}`;
    return (
      <div key={group.key} role="group" aria-labelledby={titleId} className="lab-group">
        <div className="lab-group__head">
          <span id={titleId} className="lab-group__tag" data-tone={index % 4}>
            {m.group(tag(group))}
          </span>
          <span className="lab-group__criteria">{names(group)}</span>
          {!allIn ? (
            <button type="button" className="link-button lab-group__pick" onClick={() => onChange(ids.slice(0, MAX_LAB_INTAKES))}>
              {m.onlyThisGroup}
            </button>
          ) : null}
        </div>
        {twin ? (
          <p className="lab-group__note">{m.twin(tag(twin))}</p>
        ) : null}
        <div className="lab-grid">
          {group.intakes.map((intake) => {
            const checked = selected.includes(intake.id);
            return (
              <label key={intake.id} className="lab-card" data-checked={checked}>
                <input type="checkbox" className="lab-card__input" checked={checked} disabled={!checked && full} onChange={(e) => toggle(intake.id, e.target.checked)} />
                <span className="lab-card__box" aria-hidden="true">
                  <CheckIcon size={12} />
                </span>
                <span className="lab-card__body">
                  <span className="lab-card__name">{intake.name}</span>
                  <span className="lab-card__meta">
                    {intake.with_outcome > 0 ? m.withOutcome(f.number(intake.with_outcome)) : m.noOutcome} · {m.admitted(f.number(intake.admitted))}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <section className="th-card lab-picker" aria-labelledby="lab-picker-title">
      <div className="lab-picker__head">
        <div>
          <h2 id="lab-picker-title" className="th-type-h4">
            {m.heading}
          </h2>
          <p className="muted">{m.help}</p>
        </div>
        <p className="lab-picker__summary" aria-live="polite">
          {m.summary(selected.length, f.number(outcomes))}
        </p>
      </div>

      {active.map((group) => renderGroup(group))}
      {idle.length > 0 ? (
        <details className="lab-idle" open={active.length === 0 || idle.some((g) => g.intakes.some((i) => selected.includes(i.id)))}>
          <summary>
            {m.idle(idle.reduce((n, g) => n + g.intakes.length, 0))}
          </summary>
          <div className="lab-idle__body">{idle.map((group) => renderGroup(group))}</div>
        </details>
      ) : null}

      <div className="lab-picker__foot">
        {selected.length === 0 ? (
          <p className="muted">{m.pickOne}</p>
        ) : common.length === 0 ? (
          <Alert tone="warning" title={m.noCommonTitle}>
            {m.noCommonBody}
          </Alert>
        ) : (
          <div className="lab-common">
            <span className="lab-common__label">{m.common(common.length)}</span>
            <ul className="lab-common__list">
              {common.map((c) => (
                <li key={c.id} className="lab-common__chip">
                  {c.name}
                </li>
              ))}
            </ul>
          </div>
        )}
        {full ? <p className="muted">{m.max(MAX_LAB_INTAKES)}</p> : null}
        <Button loading={running} disabled={selected.length === 0 || common.length === 0} onClick={onRun}>
          {m.run(selected.length)}
        </Button>
      </div>
    </section>
  );
}

export function LabView() {
  const m = useT(messages).lab;
  const errorText = useErrorText();
  const candidates = useGet<LabIntake[]>("/analytics/lab/intakes");
  const intakes = useMemo(() => candidates.data ?? [], [candidates.data]);
  const groups = useMemo(() => groupByCriteria(intakes), [intakes]);
  const [picked, setPicked] = useState<string[] | null>(null);
  const selected = picked ?? defaultSelection(groups);

  const lab = useSend<Lab, { intake_ids: string[] }>("POST", "/analytics/lab");
  const run = lab.variables?.intake_ids ?? null;
  const { isIdle, mutate } = lab;
  // Tự phân tích khi mở trang lần đầu với lựa chọn mặc định (nhóm tiêu chí nhiều dữ liệu nhất).
  useEffect(() => {
    const initial = defaultSelection(groups);
    if (isIdle && initial.length > 0) mutate({ intake_ids: initial });
  }, [isIdle, groups, mutate]);

  return (
    <div className="stack">
      <PageHeader title={m.title} subtitle={m.subtitle} />
      <QueryState query={candidates} lines={2}>
        {() =>
          groups.length === 0 ? (
            <Alert tone="info">{m.empty}</Alert>
          ) : (
            <>
              <DemoNotice show={intakes.some((i) => selected.includes(i.id) && i.name.startsWith("[Minh hoạ]"))} />
              <IntakePicker intakes={intakes} groups={groups} selected={selected} onChange={setPicked} running={lab.isPending} onRun={() => lab.mutate({ intake_ids: selected })} />
              {lab.isError ? <Alert tone="danger">{errorText(lab.error)}</Alert> : null}
              {lab.isPending && !lab.data ? <p className="muted">{m.analysing}</p> : null}
              {lab.data && run ? <Results key={run.join(",") + lab.data.pool} lab={lab.data} ids={run} /> : null}
            </>
          )
        }
      </QueryState>
    </div>
  );
}
