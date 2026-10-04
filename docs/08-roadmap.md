# Lộ trình và tiêu chí nghiệm thu

Phạm vi: chạy local bằng Docker Compose, chưa deploy. Mỗi mốc kết thúc bằng một bản chạy được và test xanh.

## M0 — Nền móng
- Monorepo `apps/api`, `apps/web`, `infra`; `docker-compose.yml` (Postgres + pgvector, Redis, MinIO, Mailpit để xem email local).
- FastAPI: cấu hình, kết nối DB async, Alembic, logging JSON có `request_id`, `/healthz`.
- Auth: đăng nhập bằng mật khẩu (Argon2), cookie httpOnly, refresh xoay vòng, RBAC theo permission, audit log.
- Microsoft OIDC (PKCE, nonce, định danh `iss+sub`), lời mời nhân sự.
- Next.js: layout, đăng nhập, middleware chặn route theo vai trò, API client sinh từ OpenAPI.
- Seed dữ liệu mẫu: 5 vai trò, 1 chương trình, 1 đợt tuyển.
- CI: lint (ruff, eslint), kiểm tra kiểu (mypy, tsc), test.

**Nghiệm thu:** `docker compose up` rồi đăng nhập được bằng tài khoản seed của từng vai trò, mỗi vai trò chỉ thấy menu của mình; gọi API trái quyền trả `403`; mọi thay đổi vai trò có audit.

## M1 — Tuyển sinh MVP
- Đợt tuyển, form hồ sơ động theo `form_schema`, upload tài liệu qua presigned URL, kiểm tra loại và kích thước, quét virus (ClamAV tuỳ chọn).
- State machine hồ sơ (bảng chuyển hợp lệ + quyền theo bước + khoá lạc quan), timeline.
- Rubric, màn hình reviewer, đề xuất, phê duyệt hai cấp (người duyệt khác người đề xuất, ràng buộc ở DB).
- Email thông báo qua outbox + worker.
- Yêu cầu xem xét lại.

**Nghiệm thu:** chạy trọn một hồ sơ từ nộp đến `ACCEPTED`; thử duyệt đề xuất của chính mình bị từ chối (cả ở API lẫn DB); hai người chuyển trạng thái cùng lúc thì một người nhận `409`; ứng viên không xem được sự kiện nội bộ và không xem được hồ sơ người khác.

## M2 — Dashboard tuyển sinh
- API analytics: funnel, thời gian xử lý, tải reviewer.
- Trang dashboard (Recharts), bộ lọc theo đợt.
- Schema `analytics` và view khử định danh, role DB `powerbi_reader`, export CSV; tài liệu kết nối Power BI.

**Nghiệm thu:** số liệu dashboard khớp truy vấn SQL kiểm chứng trên dữ liệu seed; view analytics không chứa tên, email, số điện thoại.

## M3 — Đào tạo và chuẩn đầu ra
- Chương trình, môn, chuẩn đầu ra, bài đánh giá, ma trận map.
- Interface `LMSConnector` + `MockLMSConnector`; job đồng bộ điểm; import CSV.
- Job tính attainment (công thức ở [05-data-model.md](05-data-model.md)); dashboard đào tạo; phát hiện khoảng trống chương trình.

**Nghiệm thu:** với bộ dữ liệu mẫu có đáp án tính tay, attainment từng chuẩn đầu ra khớp; chạy lại đồng bộ không tạo bản ghi trùng.

## M4 — Trợ lý AI
- Lớp provider (anthropic, openai, gemini, ollama, fake), cấu hình theo tác vụ.
- Kho tri thức: upload, trích văn bản, chia chunk, embedding, hybrid search.
- API chat stream, trích nguồn, từ chối khi thiếu ngữ cảnh, feedback, rate limit.
- Bộ eval và lệnh chạy eval; UI chat.
- Chấm sơ bộ AI (tuỳ chọn, ẩn đến khi reviewer chốt điểm).

**Nghiệm thu:** với provider `fake`, toàn bộ luồng chạy trong test; với provider thật (khi có key) đạt các ngưỡng eval ở [07-ai-rag.md](07-ai-rag.md); câu hỏi ngoài phạm vi bị từ chối; chunk `internal` không bao giờ xuất hiện trong câu trả lời cho ứng viên.

## M5 — Chất lượng dữ liệu và cải tiến
- Engine rule cảnh báo, quản lý vòng đời cảnh báo.
- Báo cáo cải tiến do LLM soạn từ số liệu tổng hợp, kiểm tra khớp số, duyệt, hành động cải tiến.

**Nghiệm thu:** từng rule có test với dữ liệu gây lỗi; alert không bị tạo trùng khi chạy lại; số liệu trong báo cáo khớp snapshot.

## Ngoài phạm vi hiện tại
Deploy lên cloud, connector CRM/LMS thật, SSO cấp tổ chức ngoài Microsoft, ứng dụng di động, thanh toán lệ phí.

## Rủi ro chính
| Rủi ro | Giảm thiểu |
|---|---|
| Thiên lệch hoặc sai sót của AI chấm sơ bộ | AI chỉ gợi ý, ẩn đến khi reviewer chấm xong, loại trường nhạy cảm, theo dõi độ lệch |
| Rò rỉ dữ liệu cá nhân | Mã hoá cột, presigned URL ngắn hạn, audit mọi lần xem/tải, analytics khử định danh |
| Chiếm tài khoản qua Microsoft | Định danh `iss+sub`, không gộp theo email, giới hạn tenant cho nhân sự |
| Trợ lý trả lời sai | Grounding gate, từ chối khi thiếu ngữ cảnh, eval trước khi bật |
| Chưa có CRM/LMS thật | Adapter và mock; contract test để connector thật cắm vào sau |
