"use client";

import { useId, useState, type KeyboardEvent, type ReactNode } from "react";

/** Tiêu đề trang có vạch đỏ đặc trưng, mô tả và vùng hành động. */
export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-head page-head--row">
      <div className="page-head__text">
        <h1 className="page-head__title">{title}</h1>
        {subtitle ? <p className="page-head__subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="page-head__actions">{actions}</div> : null}
    </header>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "ok" | "warn" | "bad" }) {
  return (
    <div className={`stat ${tone ? `stat--${tone}` : ""}`}>
      <div className="stat__value">{value}</div>
      <div className="stat__label">{label}</div>
      {hint ? <div className="stat__hint">{hint}</div> : null}
    </div>
  );
}

export function Progress({ value, max = 100, label, tone }: { value: number; max?: number; label: string; tone?: "ok" | "warn" | "bad" }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div
      className={`progress-bar ${tone ? `progress-bar--${tone}` : ""}`}
      role="progressbar"
      aria-label={label}
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className="progress-bar__fill" style={{ width: `${pct}%` }} />
    </div>
  );
}

export interface TabItem {
  id: string;
  label: string;
  content: ReactNode;
  badge?: ReactNode;
}

/** Tabs theo mẫu WAI-ARIA: mũi tên trái/phải đổi tab, Home/End về đầu/cuối. */
export function Tabs({ items, initial }: { items: TabItem[]; initial?: string }) {
  const base = useId();
  const [active, setActive] = useState(initial ?? items[0]?.id);

  function onKey(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = items.length - 1;
    const next = e.key === "ArrowRight" ? (index + 1) % items.length : e.key === "ArrowLeft" ? (index - 1 + items.length) % items.length : e.key === "Home" ? 0 : e.key === "End" ? last : -1;
    if (next < 0) return;
    e.preventDefault();
    const item = items[next];
    if (!item) return;
    setActive(item.id);
    document.getElementById(`${base}-tab-${item.id}`)?.focus();
  }

  const current = items.find((i) => i.id === active) ?? items[0];
  return (
    <div className="tabs">
      <div role="tablist" className="th-tablist">
        {items.map((item, index) => (
          <button
            key={item.id}
            id={`${base}-tab-${item.id}`}
            role="tab"
            type="button"
            className="th-tab"
            aria-selected={item.id === current?.id}
            aria-controls={`${base}-panel-${item.id}`}
            tabIndex={item.id === current?.id ? 0 : -1}
            onClick={() => setActive(item.id)}
            onKeyDown={(e) => onKey(e, index)}
          >
            {item.label}
            {item.badge ? <span className="tab-badge">{item.badge}</span> : null}
          </button>
        ))}
      </div>
      {current ? (
        <div role="tabpanel" id={`${base}-panel-${current.id}`} aria-labelledby={`${base}-tab-${current.id}`} className="tabs__panel" tabIndex={0}>
          {current.content}
        </div>
      ) : null}
    </div>
  );
}

/** Cột/thanh ngang đơn giản dựng bằng CSS, màu theo token, có nhãn và số đọc được bằng trình đọc màn hình. */
export function BarList({ rows, format }: { rows: { label: string; value: number; hint?: string; tone?: "info" | "ok" | "warn" | "bad" }[]; format?: (v: number) => string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="bar-list">
      {rows.map((r) => (
        <li key={r.label} className="bar-list__row">
          <span className="bar-list__label">{r.label}</span>
          <span className="bar-list__track" aria-hidden="true">
            <span className={`bar-list__fill bar-list__fill--${r.tone ?? "info"}`} style={{ width: `${(r.value / max) * 100}%` }} />
          </span>
          <span className="bar-list__value">
            {format ? format(r.value) : r.value}
            {r.hint ? <small> {r.hint}</small> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Biểu đồ cột xếp chồng theo nhóm (ví dụ phân bố điểm theo nhóm AI gợi ý). */
export function StackedHistogram({
  buckets,
  series,
  labelOf,
}: {
  buckets: number[];
  series: { key: string; label: string; tone: "ok" | "info" | "bad"; counts: Record<number, number> }[];
  labelOf: (bucket: number) => string;
}) {
  const totals = buckets.map((b) => series.reduce((sum, s) => sum + (s.counts[b] ?? 0), 0));
  const max = Math.max(1, ...totals);
  return (
    <figure className="histogram">
      <div className="histogram__plot" role="img" aria-label={`Phân bố: ${buckets.map((b, i) => `${labelOf(b)} có ${totals[i]}`).join(", ")}`}>
        {buckets.map((b, i) => (
          <div key={b} className="histogram__col">
            <div className="histogram__stack" style={{ height: `${((totals[i] ?? 0) / max) * 100}%` }}>
              {series.map((s) => (
                <span key={s.key} className={`histogram__seg histogram__seg--${s.tone}`} style={{ flexGrow: s.counts[b] ?? 0 }} />
              ))}
            </div>
            <span className="histogram__tick">{labelOf(b)}</span>
          </div>
        ))}
      </div>
      <figcaption className="histogram__legend">
        {series.map((s) => (
          <span key={s.key} className="legend-item">
            <i className={`legend-dot legend-dot--${s.tone}`} aria-hidden="true" />
            {s.label}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}

export function Pager({ total, offset, limit, onChange, label }: { total: number; offset: number; limit: number; onChange: (offset: number) => void; label: string }) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.ceil(total / limit);
  return (
    <nav className="pager" aria-label={label}>
      <button type="button" className="th-button th-button--secondary th-button--sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
        ‹ Trước
      </button>
      <span aria-live="polite">
        Trang {page}/{pages} · {total.toLocaleString("vi-VN")} mục
      </span>
      <button type="button" className="th-button th-button--secondary th-button--sm" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
        Sau ›
      </button>
    </nav>
  );
}

/** Nhãn "Dữ liệu minh hoạ" hiện cạnh mọi số liệu lấy từ bộ sinh dữ liệu tổng hợp. */
export function DemoNotice({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <p className="demo-notice" role="note">
      <strong>Dữ liệu minh hoạ.</strong> Mọi người, hồ sơ, điểm và kết quả trong đợt này là tổng hợp để trình diễn; không phải số liệu của chương trình thật.
    </p>
  );
}
