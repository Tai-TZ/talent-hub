import { expect, type Browser, type BrowserContext, type Page } from "@playwright/test";

/** Tài khoản seed cho môi trường local: <vai_trò>@northwind.test / Passw0rd!dev (xem `make seed`). */
export const PASSWORD = "Passw0rd!dev";

export async function login(page: Page, email: string, password = PASSWORD) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel(/^Mật khẩu/).fill(password);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page).toHaveURL(/\/dashboard|\/account\/password/);
}

/** Mở một ngữ cảnh trình duyệt riêng (cookie riêng) đã đăng nhập, đại diện cho một người dùng. */
export async function personaPage(browser: Browser, role: string): Promise<{ page: Page; context: BrowserContext }> {
  const context = await browser.newContext({ baseURL: "http://localhost:3000", locale: "vi-VN" });
  const page = await context.newPage();
  await login(page, `${role}@northwind.test`);
  return { page, context };
}

/** Tên duy nhất cho mỗi lần chạy để các lượt chạy song song/lặp lại không dẫm lên nhau. */
export function uniqueName(prefix: string): string {
  return `${prefix} ${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
}
