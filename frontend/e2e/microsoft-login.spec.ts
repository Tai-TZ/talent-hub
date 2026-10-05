import { expect, test, type Page } from "@playwright/test";
import { login, personaPage } from "./helpers";

/**
 * Đăng nhập Microsoft đi qua toàn bộ chuỗi thật: trình duyệt → BFF Next → backend → IdP giả (tools/mock_idp.py).
 * Chỉ chạy khi có IdP giả và backend được bật Microsoft: `make run-idp` rồi `make run-be-idp`, sau đó E2E_MICROSOFT=1.
 */
test.describe.configure({ mode: "serial" });
test.skip(!process.env["E2E_MICROSOFT"], "Cần IdP giả: make run-idp, make run-be-idp, đặt E2E_MICROSOFT=1");

const tag = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 4)}`;

/** Trên trang chọn tài khoản của IdP giả: nhập danh tính tuỳ ý. */
async function signInAtIdp(page: Page, email: string, name: string) {
  await expect(page.getByRole("heading", { name: /Mock|GIẢ LẬP/ })).toBeVisible();
  await page.getByLabel("Họ tên").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
}

test("ứng viên tự đăng ký bằng Microsoft rồi lần sau vào lại đúng tài khoản", async ({ browser }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Luồng chuyển hướng giống nhau; chạy một lần trên desktop.");
  const email = `ung.vien.${tag()}@outlook.test`;
  const context = await browser.newContext({ baseURL: "http://localhost:3000", locale: "vi-VN" });
  const page = await context.newPage();

  await page.goto("/login");
  await page.getByRole("link", { name: "Đăng nhập bằng Microsoft" }).click();
  await signInAtIdp(page, email, "Nguyễn Minh Anh");
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByText("Nguyễn Minh Anh").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Hồ sơ của tôi" }).first()).toBeVisible(); // vai trò ứng viên
  await expect(page.getByRole("link", { name: "Tài khoản" })).toHaveCount(0);

  // Đăng xuất rồi vào lại bằng cùng danh tính Microsoft (đổi email hiển thị cũng không tạo tài khoản mới).
  await page.getByRole("button", { name: "Đăng xuất" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.getByRole("link", { name: "Đăng nhập bằng Microsoft" }).click();
  await signInAtIdp(page, email, "Nguyễn Minh Anh");
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByText("Nguyễn Minh Anh").first()).toBeVisible();
  await context.close();
});

test("kẻ dựng tenant riêng đặt email trùng người khác không vào được tài khoản đó (nOAuth)", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Chạy một lần trên desktop.");
  await page.goto("/login");
  await page.getByRole("link", { name: "Đăng nhập bằng Microsoft" }).click();
  await page.getByRole("button", { name: /Kẻ Mạo Danh/ }).click();
  await expect(page).toHaveURL(/\/login\?error=account_exists/);
  await expect(page.locator(".th-alert--danger")).toContainText("Email này đã có tài khoản");
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/); // không có phiên nào được tạo
});

test("nhân sự được mời kích hoạt bằng Microsoft dù email Microsoft khác email được mời", async ({ browser }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Quản trị chạy trên desktop.");
  const invited = `giang.vien.${tag()}@northwind.test`;
  const admin = await personaPage(browser, "admin");
  const a = admin.page;
  await a.goto("/admin/users");
  await a.getByRole("button", { name: "Mời người dùng" }).click();
  const dialog = a.getByRole("dialog");
  await dialog.getByLabel("Email").fill(invited);
  await dialog.getByLabel("Họ và tên").fill("Giảng viên Mời");
  await dialog.getByLabel("Người chấm hồ sơ").check();
  await dialog.getByRole("button", { name: "Gửi lời mời" }).click();
  const link = (await dialog.locator("code").innerText()).trim();

  const guest = await browser.newContext({ baseURL: "http://localhost:3000", locale: "vi-VN" });
  const g = await guest.newPage();
  await g.goto(new URL(link).pathname);
  await g.getByRole("link", { name: "Kích hoạt bằng tài khoản Microsoft" }).click();
  await signInAtIdp(g, `email.khac.${tag()}@truong.edu.vn`, "Giảng viên Mời");
  await expect(g).toHaveURL(/\/dashboard$/);
  await expect(g.getByRole("link", { name: "Hàng đợi hồ sơ" }).first()).toBeVisible(); // quyền reviewer từ lời mời
  await Promise.all([admin.context.close(), guest.close()]);
});

test("người đã đăng nhập liên kết Microsoft, sau đó đăng nhập bằng Microsoft vào đúng tài khoản", async ({ browser }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Chạy một lần trên desktop.");
  const msEmail = `lien.ket.${tag()}@outlook.test`;
  const reviewer = await personaPage(browser, "training_manager");
  const r = reviewer.page;
  await r.goto("/account/password");
  await r.getByRole("link", { name: "Liên kết tài khoản Microsoft" }).click();
  await signInAtIdp(r, msEmail, "Người Liên Kết");
  await expect(r).toHaveURL(/\/account\/password\?linked=1/);
  await expect(r.getByText("Đã liên kết tài khoản Microsoft")).toBeVisible();
  await reviewer.context.close();

  const fresh = await browser.newContext({ baseURL: "http://localhost:3000", locale: "vi-VN" });
  const f = await fresh.newPage();
  await f.goto("/login");
  await f.getByRole("link", { name: "Đăng nhập bằng Microsoft" }).click();
  await signInAtIdp(f, msEmail, "Người Liên Kết");
  await expect(f).toHaveURL(/\/dashboard$/);
  await expect(f.getByText("training_manager (northwind)").first()).toBeVisible(); // vào đúng tài khoản đã liên kết
  await fresh.close();
});

test("đăng nhập mật khẩu vẫn hoạt động song song và nút Microsoft hiển thị đúng", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("link", { name: "Đăng nhập bằng Microsoft" })).toBeVisible();
  await login(page, "applicant@northwind.test");
  await expect(page).toHaveURL(/\/dashboard$/);
});
