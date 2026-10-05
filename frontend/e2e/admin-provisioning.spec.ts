import { expect, test } from "@playwright/test";
import { login, personaPage } from "./helpers";

/**
 * Bộ phận IT cấp tài khoản: mời → người được mời tự đặt mật khẩu → đúng quyền → khoá tài khoản thu hồi quyền truy cập.
 * Chạy trên desktop (quản trị là công việc trên máy tính); không phụ thuộc dữ liệu minh hoạ.
 */
test.describe.configure({ mode: "serial" });

test("IT mời nhân sự, người được mời kích hoạt, rồi bị khoá thì mất quyền", async ({ browser }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Quản trị chạy trên desktop.");
  const tag = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 4)}`;
  const email = `nguoicham.${tag}@northwind.test`;
  const password = "Mat-khau-moi-123!";

  const admin = await personaPage(browser, "admin");
  const a = admin.page;
  await a.goto("/admin/users");
  await a.getByRole("button", { name: "Mời người dùng" }).click();
  const dialog = a.getByRole("dialog");
  await dialog.getByLabel("Email").fill(email);
  await dialog.getByLabel("Họ và tên").fill("Người chấm thử nghiệm");
  await dialog.getByLabel("Người chấm hồ sơ").check();
  await dialog.getByRole("button", { name: "Gửi lời mời" }).click();
  await expect(dialog.getByText("Đã tạo tài khoản")).toBeVisible();
  const link = (await dialog.locator("code").innerText()).trim();
  expect(new URL(link).pathname).toMatch(/^\/invite\/[A-Za-z0-9_-]{20,}$/);
  await dialog.getByRole("button", { name: "Xong" }).click();

  // Người được mời mở link, đặt mật khẩu: admin không hề biết mật khẩu.
  const invitee = await browser.newContext({ baseURL: "http://localhost:3000", locale: "vi-VN" });
  const i = await invitee.newPage();
  await i.goto(new URL(link).pathname);
  await expect(i.getByRole("heading", { name: /Chào mừng/ })).toBeVisible();
  await i.getByLabel("Mật khẩu mới").fill("ngan");
  await i.getByLabel("Nhập lại mật khẩu").fill("ngan");
  await i.getByRole("button", { name: "Kích hoạt tài khoản" }).click();
  await expect(i.getByText(/ít nhất 10 ký tự/).last()).toBeVisible(); // kiểm tra phía client trước khi gọi máy chủ
  await i.getByLabel("Mật khẩu mới").fill(password);
  await i.getByLabel("Nhập lại mật khẩu").fill(password);
  await i.getByRole("button", { name: "Kích hoạt tài khoản" }).click();
  await expect(i).toHaveURL(/\/dashboard$/);
  await expect(i.getByRole("link", { name: "Hàng đợi hồ sơ" }).first()).toBeVisible();
  await expect(i.getByRole("link", { name: "Tài khoản" })).toHaveCount(0); // không có quyền quản trị

  // Liên kết chỉ dùng được một lần.
  const stranger = await browser.newContext({ baseURL: "http://localhost:3000", locale: "vi-VN" });
  const s = await stranger.newPage();
  await s.goto(new URL(link).pathname);
  await expect(s.getByRole("heading", { name: "Liên kết không dùng được" })).toBeVisible();

  // Admin thấy tài khoản đã hoạt động, rồi khoá.
  await a.goto("/admin/users");
  await a.getByRole("searchbox", { name: "Tìm theo tên hoặc email" }).fill(email);
  const row = a.getByRole("row").filter({ hasText: email });
  await expect(row.getByText("Hoạt động")).toBeVisible();
  await row.getByRole("button", { name: "Sửa" }).click();
  await a.getByRole("dialog").getByLabel("Trạng thái").selectOption("suspended");
  await a.getByRole("dialog").getByRole("button", { name: "Lưu thay đổi" }).click();
  await expect(row.getByText("Bị khoá")).toBeVisible();

  // Phiên của người bị khoá bị thu hồi và không đăng nhập lại được.
  const again = await browser.newContext({ baseURL: "http://localhost:3000", locale: "vi-VN" });
  const g = await again.newPage();
  await g.goto("/login");
  await g.getByLabel("Email").fill(email);
  await g.getByLabel(/^Mật khẩu/).fill(password);
  await g.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(g.locator(".th-alert--danger")).toBeVisible();
  await expect(g).toHaveURL(/\/login/);

  await Promise.all([admin.context.close(), invitee.close(), stranger.close(), again.close()]);
});

test("nhập hàng loạt có kiểm tra trước, dòng lỗi không làm hỏng dòng đúng", async ({ browser }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Quản trị chạy trên desktop.");
  const tag = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 4)}`;
  const admin = await personaPage(browser, "admin");
  const a = admin.page;
  await a.goto("/admin/users");
  await a.getByRole("button", { name: "Nhập hàng loạt" }).click();
  const dialog = a.getByRole("dialog");
  await dialog
    .getByLabel(/Danh sách tài khoản/)
    .fill(`email,họ tên,vai trò\nimp1.${tag}@northwind.test,Nguyễn Một,reviewer\nimp2.${tag}@northwind.test,Trần Hai,vai_tro_khong_co\nimp1.${tag}@northwind.test,Lặp Email,mentor`);
  await dialog.getByRole("button", { name: "Kiểm tra trước" }).click();
  await expect(dialog.getByText(/1 hợp lệ, 2 lỗi/)).toBeVisible();
  await dialog.getByRole("button", { name: /Tạo 1 tài khoản/ }).click();
  await expect(dialog.getByText(/Đã tạo: 1 tài khoản/)).toBeVisible();
  await dialog.locator(".dialog__actions").getByRole("button", { name: "Đóng" }).click();
  await a.getByRole("searchbox", { name: "Tìm theo tên hoặc email" }).fill(`imp1.${tag}`);
  await expect(a.getByRole("row").filter({ hasText: `imp1.${tag}@northwind.test` })).toHaveCount(1);
  await admin.context.close();
});

test("người dùng chưa đăng nhập không vào được khu quản trị", async ({ page }) => {
  await page.goto("/admin/users");
  await expect(page).toHaveURL(/\/login\?next=%2Fadmin%2Fusers/);
  await login(page, "reviewer@northwind.test");
  await page.goto("/admin/users");
  await expect(page.getByText("Bạn không có quyền thực hiện thao tác này.")).toBeVisible();
});
