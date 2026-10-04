import type { Messages } from "./i18n";

export interface NavItem {
  href: string;
  label: (t: Messages) => string;
  /** Permission cần có để thấy mục này (không có = ai đăng nhập cũng thấy). */
  permission?: string;
}

/** Danh mục điều hướng; mỗi giai đoạn của lộ trình bổ sung mục mới tại đây. */
export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/dashboard", label: (t) => t.nav.dashboard },
  { href: "/admin/audit-logs", label: (t) => t.nav.audit, permission: "audit.read" },
  { href: "/account/password", label: (t) => t.nav.password },
];

export function visibleNav(permissions: readonly string[]): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.permission || permissions.includes(item.permission));
}
