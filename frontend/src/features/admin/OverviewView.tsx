"use client";

import Link from "next/link";
import { Alert } from "@/components/ui/Alert";
import { BarList, PageHeader, Progress, Stat } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import type { AdminOverview } from "@/lib/contracts";
import { fmtNumber, fmtUsd } from "@/lib/format";
import { useGet } from "@/lib/hooks";
import { docStatus, intakeStatus, jobStatus, ROLE_LABELS } from "@/lib/labels";

const EMAIL_STATUS: Record<string, string> = { pending: "đang chờ", sent: "đã gửi", failed: "lỗi" };

function alertsOf(o: AdminOverview) {
  const out: { tone: "warning" | "danger"; text: string; href?: string }[] = [];
  const budgetRatio = o.ai.monthly_budget_usd > 0 ? o.ai.month_to_date_usd / o.ai.monthly_budget_usd : 0;
  if (o.ai.engine === "llm" && !o.ai.llm_configured) out.push({ tone: "danger", text: "Động cơ AI đặt là LLM nhưng chưa cấu hình khoá API. Sàng lọc sẽ quay về chế độ offline.", href: "/admin/settings" });
  if (budgetRatio >= 1) out.push({ tone: "danger", text: "Chi phí AI tháng này đã chạm trần ngân sách; các lượt chạy LLM mới bị chặn.", href: "/admin/costs" });
  else if (budgetRatio >= 0.8) out.push({ tone: "warning", text: `Chi phí AI đã dùng ${Math.round(budgetRatio * 100)}% ngân sách tháng.`, href: "/admin/costs" });
  if (o.users.locked > 0) out.push({ tone: "warning", text: `${o.users.locked} tài khoản đang bị khoá tạm do đăng nhập sai nhiều lần.`, href: "/admin/users" });
  if (o.security_24h.failed_logins >= 20) out.push({ tone: "warning", text: `${o.security_24h.failed_logins} lượt đăng nhập thất bại trong 24 giờ qua; hãy xem nhật ký.`, href: "/admin/audit-logs" });
  if ((o.email.queue["failed"] ?? 0) > 0) out.push({ tone: "warning", text: `${o.email.queue["failed"]} email gửi thất bại.` });
  if ((o.documents["failed"] ?? 0) > 0) out.push({ tone: "warning", text: `${o.documents["failed"]} tài liệu xử lý lỗi.`, href: "/admin/documents" });
  if ((o.jobs_24h["failed"] ?? 0) > 0) out.push({ tone: "warning", text: `${o.jobs_24h["failed"]} tác vụ nền thất bại trong 24 giờ qua.` });
  return out;
}

export function OverviewView() {
  const query = useGet<AdminOverview>("/admin/overview", { refetchInterval: 30_000 });
  return (
    <div className="stack">
      <PageHeader title="Tổng quan hệ thống" subtitle="Sức khoẻ vận hành của tổ chức: người dùng, bảo mật, tác vụ nền, email, tài liệu và chi phí AI." />
      <QueryState query={query} lines={6}>
        {(o) => {
          const alerts = alertsOf(o);
          const active = o.users.by_status["active"] ?? 0;
          const budget = o.ai.monthly_budget_usd;
          return (
            <>
              {alerts.length === 0 ? (
                <Alert tone="success">Không có cảnh báo nào cần xử lý.</Alert>
              ) : (
                alerts.map((a) => (
                  <Alert key={a.text} tone={a.tone}>
                    {a.text} {a.href ? <Link href={a.href}>Xem</Link> : null}
                  </Alert>
                ))
              )}

              <div className="stat-grid">
                <Stat label="Tài khoản đang hoạt động" value={fmtNumber(active)} hint={`${fmtNumber(o.users.by_status["invited"] ?? 0)} chờ chấp nhận lời mời`} />
                <Stat label="Bị khoá tạm" value={fmtNumber(o.users.locked)} tone={o.users.locked > 0 ? "warn" : "ok"} />
                <Stat label="Đề xuất chờ phê duyệt" value={fmtNumber(o.pending_decisions)} />
                <Stat label="Đăng nhập 24 giờ" value={fmtNumber(o.security_24h.logins)} hint={`${fmtNumber(o.security_24h.failed_logins)} thất bại`} tone={o.security_24h.failed_logins >= 20 ? "warn" : undefined} />
              </div>

              <div className="split split--2">
                <section className="th-card panel stack" aria-labelledby="roles-title">
                  <h2 id="roles-title" className="th-type-h4">
                    Người dùng theo vai trò
                  </h2>
                  <BarList rows={Object.entries(o.users.active_by_role).map(([role, n]) => ({ label: ROLE_LABELS[role] ?? role, value: n }))} format={fmtNumber} />
                </section>

                <section className="th-card panel stack" aria-labelledby="ai-title">
                  <h2 id="ai-title" className="th-type-h4">
                    AI và chi phí
                  </h2>
                  <dl className="summary">
                    <div>
                      <dt>Động cơ</dt>
                      <dd>
                        {o.ai.engine === "llm" ? "LLM" : "Offline (heuristic)"} · {o.ai.llm_configured ? "đã có khoá API" : "chưa có khoá API"}
                      </dd>
                    </div>
                    <div>
                      <dt>Mô hình</dt>
                      <dd>{o.ai.model}</dd>
                    </div>
                    <div>
                      <dt>Đã dùng tháng này</dt>
                      <dd>
                        {fmtUsd(o.ai.month_to_date_usd)} {budget > 0 ? `/ ${fmtUsd(budget)}` : "(không giới hạn)"}
                      </dd>
                    </div>
                  </dl>
                  {budget > 0 ? <Progress value={o.ai.month_to_date_usd} max={budget} label="Ngân sách AI tháng" tone={o.ai.month_to_date_usd >= budget ? "bad" : o.ai.month_to_date_usd >= budget * 0.8 ? "warn" : "ok"} /> : null}
                </section>
              </div>

              <div className="split split--2">
                <section className="th-card panel stack" aria-labelledby="jobs-title">
                  <h2 id="jobs-title" className="th-type-h4">
                    Tác vụ nền 24 giờ qua
                  </h2>
                  {Object.keys(o.jobs_24h).length === 0 ? <p className="muted">Chưa có tác vụ nào.</p> : <BarList rows={Object.entries(o.jobs_24h).map(([s, n]) => ({ label: jobStatus(s)[0], value: n, tone: s === "failed" ? "bad" : s === "done" ? "ok" : "info" }))} format={fmtNumber} />}
                </section>
                <section className="th-card panel stack" aria-labelledby="sys-title">
                  <h2 id="sys-title" className="th-type-h4">
                    Email và tài liệu
                  </h2>
                  <dl className="summary">
                    <div>
                      <dt>Kênh email</dt>
                      <dd>
                        {o.email.backend === "console" ? "Ghi ra nhật ký (thử nghiệm)" : o.email.backend === "smtp" ? "SMTP" : "Tắt"} ·{" "}
                        {Object.entries(o.email.queue)
                          .map(([s, n]) => `${EMAIL_STATUS[s] ?? s} ${n}`)
                          .join(", ") || "hàng đợi trống"}
                      </dd>
                    </div>
                    <div>
                      <dt>Tài liệu</dt>
                      <dd>
                        {Object.entries(o.documents)
                          .map(([s, n]) => `${docStatus(s)[0]} ${n}`)
                          .join(", ") || "chưa có"}
                      </dd>
                    </div>
                    <div>
                      <dt>Đợt tuyển</dt>
                      <dd>
                        {Object.entries(o.intakes)
                          .map(([s, n]) => `${intakeStatus(s)[0]} ${n}`)
                          .join(", ") || "chưa có"}
                      </dd>
                    </div>
                  </dl>
                </section>
              </div>
            </>
          );
        }}
      </QueryState>
    </div>
  );
}
