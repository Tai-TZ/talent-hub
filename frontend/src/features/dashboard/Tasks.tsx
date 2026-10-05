"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useMe } from "@/components/providers";
import { Skeleton } from "@/components/ui/Skeleton";
import type { AdminOverview, ApprovalRow, ApplicationSummary, CohortOverview, IntakeT, MentorLearner, ProgramT, QueuePage } from "@/lib/contracts";
import { fmtNumber } from "@/lib/format";
import { useGet } from "@/lib/hooks";
import { applicationStatus } from "@/lib/labels";

function TaskCard({ href, title, value, hint, tone }: { href: string; title: string; value: ReactNode; hint: string; tone?: "warn" | "ok" }) {
  return (
    <Link href={href} className={`th-card th-card--interactive task-card ${tone ? `task-card--${tone}` : ""}`}>
      <span className="task-card__value">{value}</span>
      <span className="link-card__title">{title}</span>
      <span className="link-card__desc">{hint}</span>
    </Link>
  );
}

function Loading() {
  return <Skeleton lines={1} />;
}

function MyApplicationCard() {
  const q = useGet<ApplicationSummary[]>("/applications/mine");
  if (q.isPending) return <Loading />;
  const latest = q.data?.[0];
  if (!latest) return <TaskCard href="/apply" title="Nộp hồ sơ ứng tuyển" value="→" hint="Chọn đợt tuyển đang mở và bắt đầu điền hồ sơ." />;
  return <TaskCard href={`/apply/${latest.id}`} title={latest.intake.name} value={applicationStatus(latest.status)[0]} hint="Theo dõi tiến trình xét tuyển của bạn." tone={latest.status === "ACCEPTED" ? "ok" : latest.status === "NEEDS_INFO" ? "warn" : undefined} />;
}

/** Đợt đang chấm: ưu tiên đợt có hồ sơ IN_ROUND để đếm hồ sơ chờ người dùng. */
function ReviewCard() {
  const intakes = useGet<IntakeT[]>("/intakes");
  const active = intakes.data?.find((i) => (i.counts["IN_ROUND"] ?? 0) > 0);
  const mine = useGet<QueuePage>(active ? `/staff/applications?intake_id=${active.id}&mine_pending=true&limit=1` : null);
  if (intakes.isPending || (active && mine.isPending)) return <Loading />;
  if (!active) return <TaskCard href="/staff/queue" title="Hàng đợi hồ sơ" value="0" hint="Chưa có hồ sơ nào đang trong vòng xét." />;
  const n = mine.data?.total ?? 0;
  return <TaskCard href={`/staff/queue?intake=${active.id}`} title="Hồ sơ chờ bạn chấm" value={fmtNumber(n)} hint={`${active.name}`} tone={n > 0 ? "warn" : "ok"} />;
}

function ApprovalCard() {
  const q = useGet<ApprovalRow[]>("/staff/approvals");
  if (q.isPending) return <Loading />;
  const mineless = (q.data ?? []).filter((r) => !r.proposed_by_me).length;
  return <TaskCard href="/staff/approvals" title="Đề xuất chờ phê duyệt" value={fmtNumber(mineless)} hint="Không tính các đề xuất do bạn lập (bốn mắt)." tone={mineless > 0 ? "warn" : "ok"} />;
}

function CohortCard() {
  const programs = useGet<ProgramT[]>("/programs");
  const cohorts = programs.data?.flatMap((p) => p.cohorts) ?? [];
  const target = cohorts.find((c) => c.status === "active") ?? cohorts.find((c) => c.status === "planned");
  const overview = useGet<CohortOverview>(target ? `/cohorts/${target.id}/overview` : null);
  if (programs.isPending || (target && overview.isPending)) return <Loading />;
  if (!target || !overview.data) return <TaskCard href="/cohorts" title="Khoá học" value="—" hint="Chưa có khoá học nào." />;
  const o = overview.data;
  if (o.accepted_waiting_enrollment > 0) return <TaskCard href={`/cohorts?cohort=${target.id}`} title="Hồ sơ đã nhận chờ ghi danh" value={fmtNumber(o.accepted_waiting_enrollment)} hint={target.name} tone="warn" />;
  return <TaskCard href={`/cohorts?cohort=${target.id}`} title="Học viên chưa có nơi thực chiến" value={fmtNumber(o.unplaced)} hint={target.name} tone={o.unplaced > 0 ? "warn" : "ok"} />;
}

function MentorCard() {
  const q = useGet<MentorLearner[]>("/mentor/learners");
  if (q.isPending) return <Loading />;
  return <TaskCard href="/mentor" title="Học viên bạn phụ trách" value={fmtNumber(q.data?.length ?? 0)} hint="Đánh giá mức năng lực kèm bằng chứng." />;
}

function AdminCard() {
  const q = useGet<AdminOverview>("/admin/overview");
  if (q.isPending) return <Loading />;
  const o = q.data;
  if (!o) return null;
  const issues = (o.users.locked > 0 ? 1 : 0) + (o.security_24h.failed_logins >= 20 ? 1 : 0) + (o.ai.engine === "llm" && !o.ai.llm_configured ? 1 : 0) + ((o.email.queue["failed"] ?? 0) > 0 ? 1 : 0);
  return <TaskCard href="/admin" title="Sức khoẻ hệ thống" value={issues === 0 ? "Ổn" : `${issues} cảnh báo`} hint="Bảo mật, email, tác vụ nền, chi phí AI." tone={issues === 0 ? "ok" : "warn"} />;
}

export function DashboardTasks() {
  const me = useMe();
  const can = (p: string) => me.permissions.includes(p);
  const cards: ReactNode[] = [];
  if (can("application.read.own")) cards.push(<MyApplicationCard key="mine" />);
  if (can("application.review")) cards.push(<ReviewCard key="review" />);
  if (can("decision.approve")) cards.push(<ApprovalCard key="approve" />);
  if (can("cohort.manage")) cards.push(<CohortCard key="cohort" />);
  if (can("mentor.assess")) cards.push(<MentorCard key="mentor" />);
  if (can("audit.read")) cards.push(<AdminCard key="admin" />);
  if (cards.length === 0) return null;
  return (
    <section aria-labelledby="tasks-title" className="stack">
      <h2 id="tasks-title" className="th-type-h4">
        Việc cần làm
      </h2>
      <div className="card-grid">{cards}</div>
    </section>
  );
}
