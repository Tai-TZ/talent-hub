"use client";

import { useState } from "react";
import { useMe } from "@/components/providers";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { SelectField, TextArea } from "@/components/ui/Fields";
import { BarList, PageHeader, Pager, Progress, Stat } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { TextField } from "@/components/ui/TextField";
import type { AiUsageRow, CostEntryPage, CostSummary } from "@/lib/contracts";
import { fmtDate, fmtNumber, fmtPct, fmtUsd, fmtVnd, fmtVndCompact } from "@/lib/format";
import { errorText, useGet, useSend } from "@/lib/hooks";
import { COST_CATEGORY_LABELS } from "@/lib/labels";

const LIMIT = 25;
const REFRESH = ["/admin/costs", "/admin/overview"];
const MANUAL = ["stipend", "infrastructure", "partner", "operations", "other"];
const TONE = { none: undefined, ok: "ok", warning: "warn", over: "bad" } as const;

function EntryForm({ onClose }: { onClose: () => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const [category, setCategory] = useState("operations");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(today);
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const add = useSend<unknown, { category: string; amount_vnd: number; occurred_on: string; description: string }>("POST", "/admin/costs/entries", { invalidate: REFRESH });
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        add.mutate({ category, amount_vnd: Number(amount), occurred_on: date, description }, { onSuccess: onClose, onError: (err) => setError(errorText(err)) });
      }}
    >
      <SelectField label="Hạng mục" value={category} onChange={(e) => setCategory(e.target.value)} help="Chi phí AI được tính tự động từ nhật ký sử dụng, không nhập tay.">
        {MANUAL.map((c) => (
          <option key={c} value={c}>
            {COST_CATEGORY_LABELS[c] ?? c}
          </option>
        ))}
      </SelectField>
      <div className="form-grid">
        <TextField label="Số tiền (VND)" type="number" min={1} step={1} required value={amount} onChange={(e) => setAmount(e.target.value)} />
        <TextField label="Ngày phát sinh" type="date" max={today} required value={date} onChange={(e) => setDate(e.target.value)} />
      </div>
      <TextArea label="Mô tả" rows={3} maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} />
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="dialog__actions">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button type="submit" loading={add.isPending} disabled={!(Number(amount) > 0)}>
          Ghi nhận chi phí
        </Button>
      </div>
    </form>
  );
}

function VoidForm({ id, onClose }: { id: string; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const send = useSend<unknown, { reason: string }>("POST", `/admin/costs/entries/${id}/void`, { invalidate: REFRESH });
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        send.mutate({ reason }, { onSuccess: onClose, onError: (err) => setError(errorText(err)) });
      }}
    >
      <p>Bút toán không bị xoá mà được đánh dấu huỷ kèm lý do, để sổ chi phí luôn truy vết được.</p>
      <TextArea label="Lý do huỷ" required rows={3} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="dialog__actions">
        <Button variant="secondary" onClick={onClose}>
          Đóng
        </Button>
        <Button type="submit" variant="danger" loading={send.isPending} disabled={reason.trim().length < 3}>
          Huỷ bút toán
        </Button>
      </div>
    </form>
  );
}

function BudgetForm({ onClose }: { onClose: () => void }) {
  const [category, setCategory] = useState("");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useSend<unknown, { category: string | null; amount_vnd: number }>("PUT", "/admin/costs/budgets", { invalidate: REFRESH });
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate({ category: category || null, amount_vnd: Number(amount) }, { onSuccess: onClose, onError: (err) => setError(errorText(err)) });
      }}
    >
      <SelectField label="Phạm vi ngân sách" value={category} onChange={(e) => setCategory(e.target.value)}>
        <option value="">Tổng ngân sách</option>
        {Object.entries(COST_CATEGORY_LABELS).map(([k, v]) => (
          <option key={k} value={k}>
            {v}
          </option>
        ))}
      </SelectField>
      <TextField label="Ngân sách (VND)" type="number" min={0} required value={amount} onChange={(e) => setAmount(e.target.value)} help="Hệ thống cảnh báo khi chi tiêu đạt 80% và 100%." />
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="dialog__actions">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button type="submit" loading={save.isPending} disabled={amount === ""}>
          Lưu ngân sách
        </Button>
      </div>
    </form>
  );
}

type Modal = "entry" | "budget" | { void: string } | null;

function Summary({ data }: { data: CostSummary }) {
  const cats = Object.entries(data.by_category).filter(([, v]) => v.amount > 0 || v.budget != null);
  return (
    <div className="stack">
      {data.alerts.length > 0 ? (
        <Alert tone="warning" title="Cảnh báo ngân sách">
          <ul className="plain-list">
            {data.alerts.map((a) => (
              <li key={a.scope}>
                {a.scope === "total" ? "Tổng chi phí" : (COST_CATEGORY_LABELS[a.scope] ?? a.scope)}: {a.status === "over" ? "vượt ngân sách" : "sắp hết ngân sách"} ({fmtPct(a.ratio)})
              </li>
            ))}
          </ul>
        </Alert>
      ) : null}
      <div className="stat-grid">
        <Stat label="Tổng chi phí" value={fmtVndCompact(data.total)} hint={data.overall.budget != null ? `Ngân sách ${fmtVnd(data.overall.budget)}` : `${fmtVnd(data.total)} · chưa đặt ngân sách`} tone={TONE[data.overall.status]} />
        <Stat label="Chi phí mỗi người được nhận" value={fmtVndCompact(data.cost_per_accepted)} hint={`${fmtNumber(data.accepted_count)} người được nhận`} />
        <Stat label="Chi phí AI" value={fmtVndCompact(data.ai.vnd)} hint={`${fmtUsd(data.ai.usd)} · ${fmtNumber(data.ai.calls)} lượt gọi · ${fmtNumber(data.ai.tokens)} token`} />
        <Stat label="Chi phí AI tháng này" value={fmtUsd(data.ai.month_to_date_usd)} hint={`Tỷ giá ${fmtNumber(data.usd_vnd_rate)} VND/USD`} />
      </div>

      <div className="split split--2">
        <section className="th-card panel stack" aria-labelledby="cat-title">
          <h2 id="cat-title" className="th-type-h4">
            Theo hạng mục
          </h2>
          {cats.length === 0 ? (
            <p className="muted">Chưa có chi phí nào.</p>
          ) : (
            <ul className="plain-list stack">
              {cats.map(([key, v]) => (
                <li key={key} className="stack">
                  <div className="row-actions">
                    <strong>{COST_CATEGORY_LABELS[key] ?? key}</strong>
                    <span>{fmtVnd(v.amount)}</span>
                    {v.budget != null ? <span className="muted">/ {fmtVnd(v.budget)}</span> : null}
                    {v.status === "warning" || v.status === "over" ? <StatusBadge entry={[v.status === "over" ? "Vượt ngân sách" : "Sắp hết", v.status === "over" ? "danger" : "warning"]} /> : null}
                  </div>
                  {v.budget != null ? <Progress value={v.amount} max={v.budget} label={`Ngân sách ${COST_CATEGORY_LABELS[key] ?? key}`} tone={TONE[v.status]} /> : null}
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="th-card panel stack" aria-labelledby="month-title">
          <h2 id="month-title" className="th-type-h4">
            Theo tháng
          </h2>
          {data.timeline.length === 0 ? <p className="muted">Chưa có dữ liệu.</p> : <BarList rows={data.timeline.map((t) => ({ label: t.month, value: t.total }))} format={fmtVnd} />}
        </section>
      </div>
    </div>
  );
}

function AiUsage() {
  const [group, setGroup] = useState("feature");
  const rows = useGet<AiUsageRow[]>(`/admin/costs/ai?group=${group}`);
  return (
    <section className="th-card panel stack" aria-labelledby="aiuse-title">
      <div className="row-actions">
        <h2 id="aiuse-title" className="th-type-h4">
          Chi tiết sử dụng AI
        </h2>
        <SelectField label="Nhóm theo" value={group} onChange={(e) => setGroup(e.target.value)}>
          <option value="feature">Tính năng</option>
          <option value="model">Mô hình</option>
          <option value="day">Ngày</option>
        </SelectField>
      </div>
      <QueryState query={rows} lines={3}>
        {(list) =>
          list.length === 0 ? (
            <p className="muted">Chưa có lượt gọi AI nào (đang chạy offline thì không phát sinh chi phí).</p>
          ) : (
            <div className="table-wrap table-wrap--scroll">
              <table className="th-table">
                <thead>
                  <tr>
                    <th scope="col">{group === "day" ? "Ngày" : group === "model" ? "Mô hình" : "Tính năng"}</th>
                    <th scope="col">Chi phí</th>
                    <th scope="col">Token vào</th>
                    <th scope="col">Token ra</th>
                    <th scope="col">Số lượt</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((r) => (
                    <tr key={r.key}>
                      <td>{r.key}</td>
                      <td>{fmtUsd(r.cost_usd)}</td>
                      <td>{fmtNumber(r.input_tokens)}</td>
                      <td>{fmtNumber(r.output_tokens)}</td>
                      <td>{fmtNumber(r.calls)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </QueryState>
    </section>
  );
}

export function CostsView() {
  const me = useMe();
  const canManage = me.permissions.includes("cost.manage");
  const summary = useGet<CostSummary>("/admin/costs/summary");
  const [category, setCategory] = useState("");
  const [offset, setOffset] = useState(0);
  const [modal, setModal] = useState<Modal>(null);
  const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
  if (category) params.set("category", category);
  const entries = useGet<CostEntryPage>(`/admin/costs/entries?${params}`);

  return (
    <div className="stack">
      <PageHeader
        title="Chi phí"
        subtitle="Sổ chi phí chương trình: phụ cấp, hạ tầng, đối tác và chi phí AI tự động tính từ nhật ký sử dụng."
        actions={
          canManage ? (
            <>
              <Button variant="secondary" onClick={() => setModal("budget")}>
                Đặt ngân sách
              </Button>
              <Button onClick={() => setModal("entry")}>Ghi nhận chi phí</Button>
            </>
          ) : null
        }
      />
      <QueryState query={summary} lines={5}>
        {(data) => <Summary data={data} />}
      </QueryState>

      <AiUsage />

      <section className="stack" aria-labelledby="entries-title">
        <h2 id="entries-title" className="th-type-h4">
          Sổ chi phí
        </h2>
        <div className="toolbar">
          <SelectField
            label="Hạng mục"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">Tất cả</option>
            {MANUAL.map((c) => (
              <option key={c} value={c}>
                {COST_CATEGORY_LABELS[c] ?? c}
              </option>
            ))}
          </SelectField>
        </div>
        <QueryState query={entries} lines={4}>
          {(page) =>
            page.items.length === 0 ? (
              <EmptyState title="Chưa có bút toán nào" />
            ) : (
              <>
                <div className="table-wrap">
                  <table className="th-table responsive-table">
                    <thead>
                      <tr>
                        <th scope="col">Ngày</th>
                        <th scope="col">Hạng mục</th>
                        <th scope="col">Số tiền</th>
                        <th scope="col">Mô tả</th>
                        <th scope="col">Nguồn</th>
                        {canManage ? <th scope="col">Thao tác</th> : null}
                      </tr>
                    </thead>
                    <tbody>
                      {page.items.map((e) => (
                        <tr key={e.id} className={e.voided ? "row-voided" : undefined}>
                          <td data-label="Ngày">{fmtDate(e.occurred_on)}</td>
                          <td data-label="Hạng mục">{COST_CATEGORY_LABELS[e.category] ?? e.category}</td>
                          <td data-label="Số tiền">{fmtVnd(e.amount_vnd)}</td>
                          <td data-label="Mô tả">
                            {e.description || "—"}
                            {e.voided ? <div className="muted">Đã huỷ: {e.void_reason}</div> : null}
                          </td>
                          <td data-label="Nguồn">{e.source === "system" ? "Hệ thống" : "Nhập tay"}</td>
                          {canManage ? (
                            <td data-label="Thao tác">
                              {!e.voided && e.source !== "system" ? (
                                <Button variant="tertiary" size="sm" onClick={() => setModal({ void: e.id })}>
                                  Huỷ
                                </Button>
                              ) : null}
                            </td>
                          ) : null}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pager total={page.total} offset={offset} limit={LIMIT} onChange={setOffset} label="Phân trang sổ chi phí" />
              </>
            )
          }
        </QueryState>
      </section>

      <Dialog open={modal === "entry"} title="Ghi nhận chi phí" size="md" onClose={() => setModal(null)}>
        <EntryForm onClose={() => setModal(null)} />
      </Dialog>
      <Dialog open={modal === "budget"} title="Đặt ngân sách" size="sm" onClose={() => setModal(null)}>
        <BudgetForm onClose={() => setModal(null)} />
      </Dialog>
      <Dialog open={typeof modal === "object" && modal !== null} title="Huỷ bút toán" size="sm" onClose={() => setModal(null)}>
        {typeof modal === "object" && modal ? <VoidForm id={modal.void} onClose={() => setModal(null)} /> : null}
      </Dialog>
    </div>
  );
}
