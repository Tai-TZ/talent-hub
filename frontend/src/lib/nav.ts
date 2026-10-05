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

export const NAV_GROUPS: Record<NavItem["group"], string | null> = {
  main: null,
  admissions: "Tuyển sinh",
  training: "Đào tạo",
  insight: "Phân tích",
  admin: "Quản trị hệ thống",
};

const text = (value: string) => () => value;

/** Danh mục điều hướng; mỗi mục chỉ hiện khi người dùng có permission tương ứng. */
export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/dashboard", label: (t) => t.nav.dashboard, group: "main" },
  { href: "/apply", label: text("Hồ sơ của tôi"), group: "admissions", permission: "application.read.own" },
  { href: "/staff/queue", label: text("Hàng đợi hồ sơ"), group: "admissions", permission: "application.read" },
  { href: "/staff/triage", label: text("Sàng lọc AI"), group: "admissions", permission: "triage.read" },
  { href: "/staff/approvals", label: text("Phê duyệt"), group: "admissions", permission: "decision.approve" },
  { href: "/intakes", label: text("Đợt tuyển"), group: "admissions", permission: "intake.manage" },
  { href: "/cohorts", label: text("Khoá học"), group: "training", permission: "cohort.read" },
  { href: "/mentor", label: text("Học viên của tôi"), group: "training", permission: "mentor.assess" },
  { href: "/analytics", label: text("Phễu và công bằng"), group: "insight", permission: "analytics.read", exact: true },
  { href: "/analytics/lab", label: text("Rubric Lab"), group: "insight", permission: "analytics.read" },
  { href: "/admin", label: text("Tổng quan hệ thống"), group: "admin", permission: "audit.read", exact: true },
  { href: "/admin/users", label: text("Tài khoản"), group: "admin", permission: "user.manage" },
  { href: "/admin/documents", label: text("Tài liệu"), group: "admin", permission: "kb.manage" },
  { href: "/admin/costs", label: text("Chi phí"), group: "admin", permission: "cost.read" },
  { href: "/admin/settings", label: text("Cài đặt"), group: "admin", permission: "user.manage" },
  { href: "/admin/audit-logs", label: (t) => t.nav.audit, group: "admin", permission: "audit.read" },
  { href: "/account/password", label: (t) => t.nav.password, group: "main" },
];

export function visibleNav(permissions: readonly string[]): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.permission || permissions.includes(item.permission));
}

export function isActive(item: NavItem, pathname: string): boolean {
  return pathname === item.href || (!item.exact && pathname.startsWith(`${item.href}/`));
}
