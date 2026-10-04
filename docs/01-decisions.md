# Quyết định kiến trúc (ADR log)

| # | Ngày | Quyết định | Lý do |
|---|------|-----------|-------|
| 1 | 2026-10-05 | Mục tiêu: **sản phẩm thật** | Cần bảo mật, audit log, khả năng scale, tích hợp CRM/LMS thực tế |
| 2 | 2026-10-05 | Backend: **FastAPI (Python)** | Thuận tiện cho LLM/RAG và phân tích dữ liệu |
| 3 | 2026-10-05 | Frontend: **Next.js (React, TypeScript)** | Theo gợi ý đề bài |
| 4 | 2026-10-05 | Database: **PostgreSQL + pgvector** | Một DB cho dữ liệu nghiệp vụ và vector RAG |
| 5 | 2026-10-05 | LLM: **lớp adapter đa provider**, gắn API key sau | Không khoá cứng vào một provider; đổi qua cấu hình |
| 6 | 2026-10-05 | Dashboard: **built-in (web) + export dataset cho Power BI** | Vận hành hằng ngày trên web; báo cáo quản lý qua Power BI |
| 7 | 2026-10-05 | CRM/LMS: **lớp adapter chung + connector giả lập (mock)** | Chưa chốt hệ thống cụ thể; sau này chỉ cần viết connector mới |
| 8 | 2026-10-05 | Đăng nhập: **email/mật khẩu + Google OAuth**, thiết kế theo OIDC để gắn SSO sau | Ứng viên đăng ký dễ; nhân sự nội bộ có thể dùng SSO |
| 9 | 2026-10-05 | Hạ tầng: **chỉ chạy local bằng Docker Compose**, chưa deploy (storage dùng chuẩn S3 qua MinIO) | Chưa cần deploy; giữ chuẩn S3/Postgres/Redis để sau này lên cloud không phải sửa code |
| 10 | 2026-10-05 | Xét tuyển: **Lọc hồ sơ → Bài test → Phỏng vấn → Phê duyệt 2 cấp** (người thẩm định đề xuất, người phê duyệt quyết định, phải là 2 người khác nhau) | Đáp ứng yêu cầu người phụ trách duyệt quyết định quan trọng |
| 11 | 2026-10-05 | AI chỉ **gợi ý**, không bao giờ tự đổi trạng thái hồ sơ | Tuân thủ human-in-the-loop, tránh thiên lệch tự động |

## Câu hỏi còn mở
- CRM/LMS thật sẽ tích hợp là gì (HubSpot, Salesforce, Moodle, Canvas, nội bộ...)?
- Quy định dữ liệu cá nhân (Nghị định 13/2023/NĐ-CP): thời gian lưu trữ, consent, quyền xoá dữ liệu — cần xác nhận với bộ phận pháp chế.
- Rubric chấm điểm cụ thể cho từng vòng và hạn mức (quota) mỗi đợt.
