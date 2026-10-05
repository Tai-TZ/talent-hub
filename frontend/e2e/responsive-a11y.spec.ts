import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

/** Mọi màn hình chính: không lỗi trợ năng nghiêm trọng (WCAG 2 A/AA) và không tràn ngang ở desktop lẫn điện thoại. */
const PAGES: { role: string; path: string; heading: RegExp }[] = [
  { role: "applicant", path: "/dashboard", heading: /Xin chào/ },
  { role: "applicant", path: "/apply", heading: /Hồ sơ của tôi/ },
  { role: "reviewer", path: "/staff/queue", heading: /Hàng đợi hồ sơ/ },
  { role: "reviewer", path: "/analytics", heading: /Phễu và công bằng/ },
  { role: "reviewer", path: "/analytics/lab", heading: /Rubric Lab/ },
  { role: "approver", path: "/staff/approvals", heading: /Phê duyệt quyết định/ },
  { role: "cohort_manager", path: "/cohorts", heading: /Khoá học/ },
  { role: "training_manager", path: "/mentor", heading: /Học viên của tôi/ },
  { role: "admin", path: "/intakes", heading: /Đợt tuyển/ },
  { role: "admin", path: "/staff/triage", heading: /Sàng lọc AI/ },
  { role: "admin", path: "/admin", heading: /Tổng quan hệ thống/ },
  { role: "admin", path: "/admin/users", heading: /Tài khoản/ },
  { role: "admin", path: "/admin/documents", heading: /Tài liệu/ },
  { role: "admin", path: "/admin/costs", heading: /Chi phí/ },
  { role: "admin", path: "/admin/settings", heading: /Cài đặt/ },
];

for (const { role, path, heading } of PAGES) {
  test(`${role} ${path}: trợ năng và bố cục`, async ({ page }) => {
    await login(page, `${role}@northwind.test`);
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    await page.waitForLoadState("networkidle");

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, "trang không được cuộn ngang").toBeLessThanOrEqual(1);

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    const serious = results.violations.filter((v) => v.impact === "critical" || v.impact === "serious");
    expect(serious.map((v) => `${v.id}: ${v.nodes.length} phần tử (${v.nodes[0]?.target.join(" ")})`)).toEqual([]);
  });
}
