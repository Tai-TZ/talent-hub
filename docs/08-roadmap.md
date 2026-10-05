# Lộ trình và tiêu chí nghiệm thu

Kịch bản mẫu: chương trình nhân tài AI theo đợt của tổ chức hư cấu Northwind University (xem [10-sample-tenant.md](10-sample-tenant.md)); nền tảng đa tổ chức ([09-multi-tenancy.md](09-multi-tenancy.md)) từ đầu để thêm trường khác bằng cấu hình. Phạm vi: chạy local bằng Docker Compose, chưa deploy. Mỗi mốc kết thúc bằng một bản chạy được và test xanh.

## M0 — Nền móng
- Monorepo `apps/api`, `apps/web`, `infra`; `docker-compose.yml` (Postgres + pgvector, Redis, MinIO, Mailpit để xem email local).
- FastAPI: cấu hình, kết nối DB async, Alembic, logging JSON có `request_id`, `/healthz`.
- Auth: đăng nhập bằng mật khẩu (Argon2), cookie httpOnly, refresh xoay vòng, RBAC theo permission, audit log.
- Microsoft OIDC (PKCE, nonce, định danh `iss+sub`), lời mời nhân sự.
- Next.js: layout, đăng nhập, middleware chặn route theo vai trò, API client sinh từ OpenAPI.
- **Đa tổ chức:** bảng `organizations`/`org_memberships`, cột `organization_id` + RLS trên mọi bảng, vai trò DB không BYPASSRLS, `SET LOCAL` mỗi transaction, xác định tổ chức từ tên miền, CLI tạo tổ chức, test cô lập chéo tổ chức tự động (kiểm tra mọi bảng có policy).
- i18n (vi mặc định, en).
- Seed dữ liệu mẫu: tổ chức `northwind` và một tổ chức thử `demo-uni`, đủ các vai trò, mẫu chương trình `ai-talent`.
- CI: lint (ruff, eslint), kiểm tra kiểu (mypy, tsc), test.

**Nghiệm thu:** `docker compose up` rồi đăng nhập được bằng tài khoản seed của từng vai trò, mỗi vai trò chỉ thấy menu của mình; gọi API trái quyền trả `403`; mọi thay đổi vai trò có audit; người dùng của `northwind` không đọc/ghi được dữ liệu của `demo-uni` qua API lẫn SQL trực tiếp bằng vai trò ứng dụng.

## M1 — Tuyển sinh MVP
- Đợt tuyển với **dãy vòng cấu hình** (chương trình mẫu: xét hồ sơ → đánh giá năng lực), form hồ sơ động theo `form_schema`, luật đủ điều kiện (chỉ gợi ý loại), upload tài liệu qua presigned URL, kiểm tra loại và kích thước, quét virus (ClamAV tuỳ chọn).
- State machine hồ sơ (bảng chuyển hợp lệ + quyền theo bước + khoá lạc quan), timeline.
- Rubric, màn hình reviewer, đề xuất, phê duyệt hai cấp (người duyệt khác người đề xuất, ràng buộc ở DB).
- Email thông báo qua outbox + worker.
- Yêu cầu xem xét lại.
- Import điểm vòng đánh giá năng lực (CSV/JSON, xem trước và báo lỗi theo dòng); hành động hàng loạt chạy nền.
- Gợi ý và xác nhận **xếp lớp** theo trình độ; nhập học tạo `enrollment`.

**Nghiệm thu:** chạy trọn một hồ sơ từ nộp đến `ACCEPTED`; thử duyệt đề xuất của chính mình bị từ chối (cả ở API lẫn DB); hai người chuyển trạng thái cùng lúc thì một người nhận `409`; ứng viên không xem được sự kiện nội bộ và không xem được hồ sơ người khác.

## M2 — Dashboard tuyển sinh
- API analytics: funnel, thời gian xử lý, tải reviewer.
- Trang dashboard (Recharts), bộ lọc theo đợt.
- Schema `analytics` và view khử định danh, role DB `powerbi_reader`, export CSV; tài liệu kết nối Power BI.

**Nghiệm thu:** số liệu dashboard khớp truy vấn SQL kiểm chứng trên dữ liệu seed; view analytics không chứa tên, email, số điện thoại.

## M3 — Khoá học, năng lực, thực chiến
- Program → Cohort → Phase → Track; mở/đóng phase; gán nhánh có kiểm tra sức chứa.
- Khung năng lực (thang mức SFIA và thang phần trăm), bài đánh giá, ma trận map.
- Đối tác, vị trí thực chiến, vai trò mentor và đánh giá năng lực theo mức.
- Quy tắc xét đạt (chỉ đề xuất, cohort_manager chốt); sổ phụ cấp (chỉ ghi nhận); kết quả việc làm.
- Interface `LMSConnector` + `MockLMSConnector`; job đồng bộ điểm; import CSV.
- Job tính attainment (công thức ở [05-data-model.md](05-data-model.md)); dashboard đào tạo và so sánh giữa các khoá; phát hiện khoảng trống chương trình.

**Nghiệm thu:** với bộ dữ liệu mẫu có đáp án tính tay, attainment từng năng lực khớp ở cả hai thang; mentor chỉ thấy học viên được giao; không thể đặt `qualified` mà thiếu người chốt và audit; chạy lại đồng bộ không tạo bản ghi trùng.

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
Deploy lên cloud, database riêng cho từng tổ chức, chi trả phụ cấp thực tế, engine làm bài trắc nghiệm tích hợp (trừ khi tổ chức triển khai yêu cầu), connector CRM/LMS thật, SSO cấp tổ chức ngoài Microsoft, ứng dụng di động, thanh toán lệ phí.

## Rủi ro chính
| Rủi ro | Giảm thiểu |
|---|---|
| Thiên lệch hoặc sai sót của AI chấm sơ bộ | AI chỉ gợi ý, ẩn đến khi reviewer chấm xong, loại trường nhạy cảm, theo dõi độ lệch |
| Rò rỉ dữ liệu cá nhân | Mã hoá cột, presigned URL ngắn hạn, audit mọi lần xem/tải, analytics khử định danh |
| Chiếm tài khoản qua Microsoft | Định danh `iss+sub`, không gộp theo email, giới hạn tenant cho nhân sự |
| Trợ lý trả lời sai | Grounding gate, từ chối khi thiếu ngữ cảnh, eval trước khi bật |
| Rò rỉ dữ liệu giữa các tổ chức | RLS bắt buộc, vai trò DB không BYPASSRLS, test cô lập chạy trong CI, ngữ cảnh đặt bằng `SET LOCAL` |
| Đặc thù của tổ chức triển khai chưa có (rubric, tiêu chí xét đạt, bài test) | Mọi thứ nằm trong cấu hình; danh sách cần cung cấp ở [10-sample-tenant.md](10-sample-tenant.md) mục 6; bàn giao dữ liệu đó là điều kiện để chạy khoá thật |
| Chưa có CRM/LMS thật | Adapter và mock; contract test để connector thật cắm vào sau |
