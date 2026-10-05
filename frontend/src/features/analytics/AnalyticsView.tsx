"use client";

import { IntakePicker } from "@/components/IntakePicker";
import { Alert } from "@/components/ui/Alert";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { BarList, DemoNotice, PageHeader, Stat } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import type { Fairness, Funnel, IntakeT } from "@/lib/contracts";
import { fmtNumber, fmtPct } from "@/lib/format";
import { useGet } from "@/lib/hooks";
import { outcomeLabel } from "@/lib/labels";
import { useIntakeSelection } from "@/lib/use-intake-selection";

const ATTRIBUTE_LABELS: Record<string, string> = { gender: "Giới tính (tự khai)", region: "Khu vực" };
const GROUP_LABELS: Record<string, string> = { female: "Nữ", male: "Nam", other: "Khác", khong_khai: "Không khai" };
const STAGE_LABELS: Record<string, string> = { accepted: "Được nhận" };

function FunnelPanel({ data }: { data: Funnel }) {
  const first = data.stages[0]?.count ?? 0;
  return (
    <div className="stack">
      <div className="stat-grid">
        <Stat label="Đã nộp hồ sơ" value={fmtNumber(first)} />
        <Stat label="Lấp đầy chỉ tiêu" value={fmtPct(data.quota_fill)} hint={`Chỉ tiêu ${fmtNumber(data.intake.quota)}`} tone={(data.quota_fill ?? 0) >= 1 ? "ok" : undefined} />
        <Stat label="Thời gian ra quyết định (trung vị)" value={data.median_days_to_decision != null ? `${data.median_days_to_decision} ngày` : "—"} hint="Từ lúc nộp đến khi có kết quả" />
      </div>
      <section className="th-card panel stack" aria-labelledby="funnel-title">
        <h2 id="funnel-title" className="th-type-h4">
          Phễu tuyển sinh
        </h2>
        <BarList
          rows={data.stages.map((s, i) => {
            const prev = i === 0 ? s.count : (data.stages[i - 1]?.count ?? 0);
            return { label: s.label, value: s.count, hint: i === 0 || prev === 0 ? "" : `${fmtPct(s.count / prev)} so với bước trước` };
          })}
          format={fmtNumber}
        />
        <p className="muted">
          Kết quả đã duyệt:{" "}
          {Object.entries(data.decisions).length === 0
            ? "chưa có"
            : Object.entries(data.decisions)
                .map(([k, v]) => `${outcomeLabel(k)[0]} ${fmtNumber(v)}`)
                .join(" · ")}
        </p>
      </section>
    </div>
  );
}

function FairnessPanel({ data }: { data: Fairness }) {
  const stages = Object.entries(data.stages);
  return (
    <section className="th-card panel stack" aria-labelledby="fair-title">
      <h2 id="fair-title" className="th-type-h4">
        Giám sát công bằng
      </h2>
      <p className="muted">{data.note}</p>
      {data.warnings.length > 0 ? (
        <Alert tone="warning" title="Cần rà soát">
          <ul className="plain-list">
            {data.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Alert>
      ) : (
        <Alert tone="success">Chưa thấy chênh lệch dưới ngưỡng bốn phần năm ở các nhóm đủ lớn.</Alert>
      )}
      {stages.map(([stage, attrs]) => (
        <div key={stage} className="stack">
          <h3 className="th-type-h5">{STAGE_LABELS[stage] ?? `Vào ${stage.replace("reached_", "vòng ")}`}</h3>
          <div className="split split--2">
            {Object.entries(attrs).map(([attr, g]) => (
              <div key={attr} className="stack">
                <p className="row-actions">
                  <strong>{ATTRIBUTE_LABELS[attr] ?? attr}</strong>
                  {g.impact_ratio != null ? <StatusBadge entry={[`Tỉ lệ tác động ${g.impact_ratio.toFixed(2)}`, g.impact_ratio < 0.8 ? "warning" : "success"]} /> : <span className="muted">chưa đủ dữ liệu so sánh</span>}
                </p>
                {Object.values(g.rates).every((r) => r === 0) ? (
                  <p className="muted">Chưa có ai ở giai đoạn này nên chưa so sánh được.</p>
                ) : (
                  <BarList
                    rows={Object.entries(g.rates).map(([group, rate]) => ({
                      label: GROUP_LABELS[group] ?? group,
                      value: rate,
                      hint: `n=${fmtNumber(g.sizes[group] ?? 0)}`,
                      tone: "info" as const,
                    }))}
                    format={(v) => fmtPct(v, 1)}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
      <p className="muted">Chỉ thống kê gộp nhóm; thuộc tính tự khai không bao giờ đưa vào chấm điểm. Nhóm dưới 20 người không được so sánh để tránh kết luận sai.</p>
    </section>
  );
}

const hasOutcomes = (i: IntakeT) => (i.counts["ACCEPTED"] ?? 0) + (i.counts["ENROLLED"] ?? 0) > 0;

export function AnalyticsView() {
  const { query: intakesQuery, intakes, selected, select } = useIntakeSelection(hasOutcomes);
  const id = selected?.id;
  const funnel = useGet<Funnel>(id ? `/analytics/funnel?intake_id=${id}` : null);
  const fairness = useGet<Fairness>(id ? `/analytics/fairness?intake_id=${id}` : null);

  return (
    <div className="stack">
      <PageHeader title="Phễu và công bằng" subtitle="Theo dõi ứng viên rơi rụng ở đâu và quy trình có đối xử đồng đều giữa các nhóm hay không." />
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
