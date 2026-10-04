import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Cần: `make db-up migrate seed run-be` (tài khoản seed: <vai_trò>@northwind.test / Passw0rd!dev).
const PASSWORD = "Passw0rd!dev";

async function login(page: Page, email: string, password = PASSWORD) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel(/^Mật khẩu/).fill(password);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
}

test("trang đăng nhập không có lỗi trợ năng nghiêm trọng", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Đăng nhập" })).toBeVisible();
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(results.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
});

test("chưa đăng nhập thì bị chuyển về trang đăng nhập và quay lại đúng trang sau khi đăng nhập", async ({ page }) => {
  await page.goto("/admin/audit-logs");
  await expect(page).toHaveURL(/\/login\?next=%2Fadmin%2Faudit-logs/);
  await page.getByLabel("Email").fill("admin@northwind.test");
  await page.getByLabel(/^Mật khẩu/).fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page).toHaveURL(/\/admin\/audit-logs$/);
  await expect(page.getByRole("heading", { name: "Nhật ký hoạt động" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "auth.login" }).first()).toBeVisible();
});

test("sai mật khẩu hiển thị thông báo rõ ràng và không lộ tài khoản có tồn tại hay không", async ({ page }) => {
  await login(page, "admin@northwind.test", "sai-mat-khau");
  await expect(page.locator(".th-alert--danger")).toContainText("Email hoặc mật khẩu không đúng");
  await login(page, "khong-ton-tai@northwind.test", "sai-mat-khau");
  await expect(page.locator(".th-alert--danger")).toContainText("Email hoặc mật khẩu không đúng");
});

test("người dùng chỉ thấy chức năng đúng vai trò", async ({ page }) => {
  await login(page, "applicant@northwind.test");
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: /Xin chào/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Nhật ký hoạt động" })).toHaveCount(0);

  // Gõ thẳng URL của trang quản trị: không có quyền thì chỉ thấy thông báo, không có dữ liệu.
  await page.goto("/admin/audit-logs");
  await expect(page.getByText("Bạn không có quyền xem nhật ký hoạt động.")).toBeVisible();
});

test("đăng xuất xoá phiên", async ({ page }) => {
  await login(page, "reviewer@northwind.test");
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.getByRole("button", { name: "Đăng xuất" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
});

test("menu di động mở bằng nút và đóng bằng phím Escape", async ({ page, isMobile }) => {
  test.skip(!isMobile, "chỉ áp dụng cho màn hình nhỏ");
  await login(page, "admin@northwind.test");
  await page.getByRole("button", { name: "Mở menu" }).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("link", { name: "Nhật ký hoạt động" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
});

test("không bị tràn ngang trên mọi kích thước", async ({ page }) => {
  await login(page, "admin@northwind.test");
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto("/admin/audit-logs");
  await expect(page.getByRole("heading", { name: "Nhật ký hoạt động" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
