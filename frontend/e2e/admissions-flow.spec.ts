import { expect, test } from "@playwright/test";
import { personaPage, uniqueName } from "./helpers";

/**
 * Luồng tuyển sinh đầy đủ qua giao diện, mỗi bước do đúng vai trò thực hiện:
 * Quản trị tạo đợt + rubric + mở → Ứng viên nộp hồ sơ → Quản trị đóng, bắt đầu vòng, chạy sàng lọc AI →
 * Người chấm chốt điểm (AI mở khoá sau đó) và đề xuất → Người phê duyệt duyệt → Ứng viên thấy kết quả.
 */
test.describe.configure({ mode: "serial" });

const ESSAY =
  "Tôi đã xây dựng một chatbot tư vấn tuyển sinh bằng Python và FastAPI cho câu lạc bộ của trường, phục vụ hơn năm trăm sinh viên mỗi tuần. " +
  "Tôi muốn học AI ứng dụng bài bản để đưa các sản phẩm như vậy vào dùng thật, cùng đội ngũ có kinh nghiệm triển khai ở doanh nghiệp.";

test("tuyển sinh từ tạo đợt đến công bố kết quả", async ({ browser }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Luồng đầy đủ chạy trên desktop; mobile có kiểm thử riêng cho cổng ứng viên.");
  test.setTimeout(240_000);
  const intakeName = uniqueName("E2E đợt tuyển");

  // ---------- 1. Quản trị: tạo đợt, rubric, mở ----------
  const admin = await personaPage(browser, "admin");
  const a = admin.page;
  await a.goto("/intakes");
  await a.getByRole("button", { name: "Tạo đợt tuyển" }).click();
  const dialog = a.getByRole("dialog");
  await dialog.getByLabel("Tên đợt tuyển").fill(intakeName);
  await dialog.getByLabel("Số người chấm tối thiểu mỗi hồ sơ").fill("1");
  await dialog.getByLabel(/Dùng AI hỗ trợ sàng lọc/).check();
  await dialog.getByRole("button", { name: "Tạo đợt tuyển nháp" }).click();
  await expect(a).toHaveURL(/\/intakes\/[0-9a-f-]{36}$/);
  const intakeId = a.url().split("/").at(-1)!;
  await expect(a.getByRole("heading", { name: intakeName })).toBeVisible();

  for (const round of ["Xét hồ sơ", "Đánh giá năng lực"]) {
    const section = a.getByRole("region", { name: `Rubric ${round}` });
    await section.getByRole("button", { name: /Dùng mẫu 7 tiêu chí/ }).click();
    await section.getByRole("button", { name: "Lưu rubric" }).click();
    await expect(section.getByText("Đã lưu rubric")).toBeVisible();
  }
  await a.getByRole("button", { name: "Mở đợt tuyển" }).click();
  await expect(a.getByText("Đã mở đợt tuyển")).toBeVisible();

  // ---------- 2. Ứng viên: nộp hồ sơ ----------
  const applicant = await personaPage(browser, "applicant");
  const p = applicant.page;
  await p.goto("/apply");
  await p.locator("article", { hasText: intakeName }).getByRole("button", { name: "Bắt đầu ứng tuyển" }).click();
  await expect(p).toHaveURL(/\/apply\/[0-9a-f-]{36}$/);
  const applicationId = p.url().split("/").at(-1)!;

  await p.getByLabel("Số điện thoại").fill("0901234567");
  await p.getByRole("button", { name: "Tiếp tục" }).click();
  await p.getByRole("button", { name: "Thêm học vấn" }).click();
  await p.getByLabel("Trường").fill("Đại học Northwind University");
  await p.getByLabel("Ngành học").fill("Khoa học máy tính");
  await p.getByRole("button", { name: "Tiếp tục" }).click();
  await p.getByRole("button", { name: "Thêm dự án" }).click();
  await p.getByLabel("Tên dự án").fill("Chatbot tư vấn tuyển sinh");
  await p.getByLabel(/Mô tả \(vai trò/).fill("Xây dựng chatbot bằng Python và FastAPI, phục vụ 500 sinh viên mỗi tuần.");
  await p.getByRole("button", { name: "Tiếp tục" }).click();
  await p.getByRole("textbox", { name: /^Kỹ năng/ }).fill("Python, SQL, học máy, FastAPI");
  await p.getByRole("button", { name: "Tiếp tục" }).click();
  await p.getByLabel(/Vì sao bạn muốn tham gia/).fill(ESSAY);
  await p.getByRole("button", { name: "Tiếp tục" }).click();
  await p.getByLabel(/Tôi xác nhận thông tin/).check();
  await p.getByRole("button", { name: "Nộp hồ sơ" }).click();
  await expect(p.getByRole("heading", { name: "Tình trạng hồ sơ" })).toBeVisible();
  await expect(p.locator(".th-badge", { hasText: "Đã nộp" })).toBeVisible();

  // ---------- 3. Quản trị: đóng, bắt đầu vòng, sàng lọc AI ----------
  await a.reload();
  await a.getByRole("button", { name: "Đóng nhận hồ sơ" }).click();
  await expect(a.getByText("Đã đóng nhận hồ sơ")).toBeVisible();
  await a.getByRole("button", { name: "Bắt đầu vòng đầu" }).click();
  await expect(a.getByText("Đã chuyển 1 hồ sơ vào vòng đầu")).toBeVisible();

  await a.goto(`/staff/triage?intake=${intakeId}`);
  await a.getByRole("button", { name: "Chạy sàng lọc hồ sơ chưa chấm" }).click();
  await expect(a.getByText("Đã sàng lọc xong")).toBeVisible({ timeout: 60_000 });
  await expect(a.getByText("Chấm 1 hồ sơ")).toBeVisible();

  // ---------- 4. Người chấm: AI bị khoá tới khi chốt điểm, rồi đề xuất ----------
  const reviewer = await personaPage(browser, "reviewer");
  const r = reviewer.page;
  await r.goto(`/staff/applications/${applicationId}`);
  await expect(r.getByText("Gợi ý AI đang được ẩn")).toBeVisible();
  await expect(r.getByText(/Điểm gợi ý/)).toHaveCount(0); // chống neo: chưa thấy điểm AI
  await expect(r.getByText("Chatbot tư vấn tuyển sinh", { exact: true })).toBeVisible();

  for (const criterion of ["Dự án thực tế", "Lập trình", "Nền tảng AI/ML", "Học vấn", "Kinh nghiệm", "Động lực", "Giao tiếp"]) {
    await r.getByRole("group", { name: new RegExp(criterion) }).getByText("3", { exact: true }).click();
  }
  await r.getByLabel("Cho đi tiếp").check();
  await r.getByRole("button", { name: "Chốt điểm" }).click();
  await expect(r.getByRole("heading", { name: "Điểm của bạn" })).toBeVisible();
  await expect(r.getByText(/Điểm gợi ý/)).toBeVisible(); // AI mở khoá sau khi tự chấm
  await expect(r.getByText("Gợi ý AI đang được ẩn")).toHaveCount(0);

  await r.getByRole("button", { name: "Đề xuất quyết định" }).click();
  await r.getByRole("dialog").getByLabel(/^Lý do/).fill("Dự án chatbot có sản phẩm thật, phù hợp tiêu chí dự án và lập trình của đợt.");
  await r.getByRole("dialog").getByRole("button", { name: "Gửi đề xuất" }).click();
  await expect(r.locator(".th-badge", { hasText: "Chờ phê duyệt" })).toBeVisible();

  // Người đề xuất không tự duyệt được (bốn mắt): chỉ người phê duyệt khác thấy nút Duyệt.
  // ---------- 5. Người phê duyệt ----------
  const approver = await personaPage(browser, "approver");
  const v = approver.page;
  await v.goto("/staff/approvals");
  const row = v.getByRole("row").filter({ hasText: intakeName });
  await expect(row).toHaveCount(1);
  await row.getByRole("button", { name: "Duyệt" }).click();
  const approve = v.getByRole("dialog");
  await approve.getByLabel(/^Lý do quyết định/).fill("Đồng ý với đề xuất: hồ sơ có dự án thực tế và điểm chấm đạt ngưỡng.");
  await approve.getByLabel(/^Lời nhắn gửi ứng viên/).fill("Chúc mừng bạn đã trúng tuyển. Chương trình sẽ liên hệ hướng dẫn nhập học.");
  await approve.getByRole("button", { name: "Phê duyệt" }).click();
  await expect(v.getByRole("row").filter({ hasText: intakeName })).toHaveCount(0);

  // ---------- 6. Ứng viên thấy kết quả và nhận thông báo ----------
  await p.goto(`/apply/${applicationId}`);
  await expect(p.getByText(/Chúc mừng! Hồ sơ của bạn đã được nhận/)).toBeVisible();
  await p.goto("/dashboard");
  await expect(p.getByText("Chúc mừng, hồ sơ của bạn được nhận")).toBeVisible();

  await Promise.all([admin.context.close(), applicant.context.close(), reviewer.context.close(), approver.context.close()]);
});
