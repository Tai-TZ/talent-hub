import { expect, test } from "@playwright/test";
import { personaPage } from "./helpers";

/**
 * Quản trị › Tích hợp: tạo khoá có phạm vi → khoá hiện đúng một lần → hệ thống ngoài dùng khoá gọi API qua BFF
 * (không cookie) → thu hồi thì bị từ chối ngay.
 */
test("IT tạo khoá tích hợp, Power BI đọc được dữ liệu, thu hồi thì mất quyền", async ({ browser, playwright, baseURL }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Quản trị chạy trên desktop.");
  const name = `E2E Power BI ${Date.now().toString(36)}`;
  const { page } = await personaPage(browser, "admin");
  await page.goto("/admin/integrations");
  await page.getByRole("button", { name: "Tạo khoá" }).first().click();
  const form = page.getByRole("dialog");
  await form.getByLabel("Tên khoá").fill(name);
  await form.getByRole("button", { name: "Tạo khoá" }).click();

  const created = page.getByRole("dialog", { name: "Khoá đã được tạo" });
  await expect(created.getByText(/không xem lại được nữa/)).toBeVisible();
  const token = (await created.locator(".secret code").textContent())?.trim() ?? "";
  expect(token).toMatch(/^thk_[0-9a-f]{8}_/);
  await created.getByRole("button", { name: "Tôi đã lưu khoá" }).click();
  const row = page.getByRole("row", { name: new RegExp(name) });
  await expect(row.getByText("Đang hoạt động")).toBeVisible();
  await expect(page.getByText(token)).toHaveCount(0); // khoá gốc không hiện lại

  const external = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer ${token}` } });
  const csv = await external.get("/api/v1/integrations/exports/applications.csv");
  expect(csv.status()).toBe(200);
  expect((await csv.text()).split("\n")[0]).toContain("candidate_code");
  expect((await external.get("/api/v1/integrations/crm/applications")).status()).toBe(403); // ngoài phạm vi

  await row.getByRole("button", { name: "Thu hồi" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Thu hồi khoá" }).click();
  await expect(row.getByText("Đã thu hồi")).toBeVisible();
  expect((await external.get("/api/v1/integrations/exports/applications.csv")).status()).toBe(401);
  await external.dispose();
});
