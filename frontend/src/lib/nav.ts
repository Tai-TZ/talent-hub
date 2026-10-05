import type { Messages } from "./i18n";

export interface NavItem {
  href: string;
  label: (t: Messages) => string;
  group: "main" | "admissions" | "training" | "insight" | "admin";
  /** Permission cần có để thấy mục này (không có = ai đăng nhập cũng thấy). */
  permission?: string;
  /** Chỉ coi là đang ở mục này khi đúng đường dẫn (cho mục cha như /admin). */
  exact?: boolean;
}

/** Tiêu đề nhóm menu (null = không có tiêu đề). */
export const NAV_GROUPS: Record<NavItem["group"], ((t: Messages) => string) | null> = {
  main: null,
  admissions: (t) => t.nav.groups.admissions,
  training: (t) => t.nav.groups.training,
  insight: (t) => t.nav.groups.insight,
  admin: (t) => t.nav.groups.admin,
};

/** Danh mục điều hướng; mỗi mục chỉ hiện khi người dùng có permission tương ứng. */
export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/dashboard", label: (t) => t.nav.dashboard, group: "main" },
  { href: "/apply", label: (t) => t.nav.items.myApplications, group: "admissions", permission: "application.read.own" },
  { href: "/staff/queue", label: (t) => t.nav.items.queue, group: "admissions", permission: "application.read" },
  { href: "/staff/triage", label: (t) => t.nav.items.triage, group: "admissions", permission: "triage.read" },
  { href: "/staff/approvals", label: (t) => t.nav.items.approvals, group: "admissions", permission: "decision.approve" },
  { href: "/intakes", label: (t) => t.nav.items.intakes, group: "admissions", permission: "intake.manage" },
  { href: "/cohorts", label: (t) => t.nav.items.cohorts, group: "training", permission: "cohort.read" },
  { href: "/mentor", label: (t) => t.nav.items.mentees, group: "training", permission: "mentor.assess" },
  { href: "/analytics", label: (t) => t.nav.items.funnel, group: "insight", permission: "analytics.read", exact: true },
  { href: "/analytics/lab", label: (t) => t.nav.items.lab, group: "insight", permission: "analytics.read" },
  { href: "/analytics/quality", label: (t) => t.nav.items.quality, group: "insight", permission: "analytics.read" },
  { href: "/admin", label: (t) => t.nav.items.adminOverview, group: "admin", permission: "audit.read", exact: true },
  { href: "/admin/users", label: (t) => t.nav.items.accounts, group: "admin", permission: "user.manage" },
  { href: "/admin/documents", label: (t) => t.nav.items.documents, group: "admin", permission: "kb.manage" },
  { href: "/admin/costs", label: (t) => t.nav.items.costs, group: "admin", permission: "cost.read" },
  { href: "/admin/settings", label: (t) => t.nav.items.settings, group: "admin", permission: "user.manage" },
  { href: "/admin/audit-logs", label: (t) => t.nav.audit, group: "admin", permission: "audit.read" },
];

export function visibleNav(permissions: readonly string[]): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.permission || permissions.includes(item.permission));
}

export function isActive(item: NavItem, pathname: string): boolean {
  return pathname === item.href || (!item.exact && pathname.startsWith(`${item.href}/`));
}
