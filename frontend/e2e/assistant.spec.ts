import { expect, test } from "@playwright/test";
import { personaPage } from "./helpers";

/** Trợ lý hỏi đáp: câu trả lời có nguồn bấm được, từ chối khi không có căn cứ, ứng viên không thấy tài liệu nội bộ. */
test("ứng viên hỏi trợ lý: có nguồn, từ chối khi không có căn cứ, đánh giá được câu trả lời", async ({ browser }) => {
  const applicant = await personaPage(browser, "applicant");
  const page = applicant.page;
  await page.goto("/apply");
  await page.getByRole("button", { name: "Hỏi trợ lý" }).click();
  const dialog = page.getByRole("dialog", { name: "Trợ lý hỏi đáp" });
  await expect(dialog.getByText(/luôn kèm nguồn/)).toBeVisible();

  await dialog.getByRole("button", { name: "Phụ cấp hàng tháng là bao nhiêu?" }).click();
  await expect(dialog.getByText(/tám triệu đồng/)).toBeVisible();
  const source = dialog.getByRole("button", { name: /^\[1\] .*Phụ cấp và quyền lợi/ });
  await expect(source).toBeVisible();
  await source.click();
  await expect(dialog.locator("blockquote")).toContainText("tám triệu");

  await dialog.getByRole("button", { name: "Có", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Có", exact: true })).toHaveAttribute("aria-pressed", "true");

  await dialog.getByLabel("Câu hỏi của bạn").fill("Thời tiết Hà Nội hôm nay thế nào?");
  await dialog.getByRole("button", { name: "Gửi" }).click();
  await expect(dialog.getByText(/chưa tìm thấy thông tin này/)).toBeVisible();

  // Tài liệu nội bộ không lộ cho ứng viên.
  await dialog.getByLabel("Câu hỏi của bạn").fill("Quyết định ngoại lệ khi khác gợi ý được ghi nhận thế nào?");
  await dialog.getByLabel("Câu hỏi của bạn").press("Enter");
  await expect(dialog.getByText(/chưa tìm thấy thông tin này/)).toHaveCount(2);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await applicant.context.close();
});

test("IT thấy câu hỏi chưa trả lời được để biết cần bổ sung tài liệu nào", async ({ browser }) => {
  const gap = `Chương trình có xe đưa đón học viên ${Date.now().toString(36)} không?`;
  const applicant = await personaPage(browser, "applicant");
  await applicant.page.goto("/apply");
  await applicant.page.getByRole("button", { name: "Hỏi trợ lý" }).click();
  const dialog = applicant.page.getByRole("dialog", { name: "Trợ lý hỏi đáp" });
  await dialog.getByLabel("Câu hỏi của bạn").fill(gap);
  await dialog.getByRole("button", { name: "Gửi" }).click();
  await expect(dialog.getByText(/chưa tìm thấy thông tin này/)).toBeVisible();
  await applicant.context.close();

  const admin = await personaPage(browser, "admin");
  await admin.page.goto("/admin/documents");
  await expect(admin.page.getByRole("heading", { name: /Chất lượng trợ lý hỏi đáp/ })).toBeVisible();
  await expect(admin.page.getByText(gap)).toBeVisible();
  await admin.context.close();
});
