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
| 8 | 2026-10-05 | Đăng nhập: **tài khoản do admin cấp** (không có tự đăng ký) **hoặc tài khoản Microsoft** (OIDC; định danh bằng `iss+sub`, không dùng email để gộp tài khoản vì lỗ hổng nOAuth; nhân sự gắn qua link mời, ứng viên tự tạo tài khoản applicant) | Kiểm soát chặt người truy cập; đồng bộ hệ sinh thái Microsoft (Power BI, Microsoft 365) |
| 9 | 2026-10-05 | Hạ tầng: **chỉ chạy local bằng Docker Compose**, chưa deploy (storage dùng chuẩn S3 qua MinIO) | Chưa cần deploy; giữ chuẩn S3/Postgres/Redis để sau này lên cloud không phải sửa code |
| 10 | 2026-10-05 | Xét tuyển: **dãy vòng cấu hình theo đợt** (Northwind University: xét hồ sơ → đánh giá năng lực → xếp lớp), **phê duyệt 2 cấp** (người đề xuất và người duyệt phải khác nhau) | Đáp ứng yêu cầu người phụ trách duyệt quyết định quan trọng; mỗi trường có quy trình khác nhau |
| 11 | 2026-10-05 | AI chỉ **gợi ý**, không bao giờ tự đổi trạng thái hồ sơ | Tuân thủ human-in-the-loop, tránh thiên lệch tự động |
| 12 | 2026-10-05 | **Khách hàng đầu tiên là Northwind University** (chương trình nhân tài AI thực chiến); thiết kế **đa tổ chức** để thêm trường khác | Yêu cầu của chủ dự án: làm riêng cho Northwind University nhưng phải mở rộng được |
| 13 | 2026-10-05 | Đa tổ chức: **1 DB, 1 schema, `organization_id` + RLS** (FORCE, vai trò app không BYPASSRLS, `SET LOCAL` mỗi transaction), test cô lập chéo tổ chức trong CI | Chi phí vận hành thấp nhất, vẫn cô lập ở tầng DB; xem [09-multi-tenancy.md](09-multi-tenancy.md) |
| 14 | 2026-10-05 | Phần đặc thù của từng trường nằm trong **mẫu chương trình (program template)** dạng cấu hình, không nằm trong code | Thêm trường mới bằng cấu hình |
| 15 | 2026-10-05 | Mô hình chương trình: **Program → Cohort → Phase → Track**; khung năng lực hỗ trợ cả thang mức (SFIA) lẫn thang phần trăm (PLO) | Chương trình mẫu là khoá 12 tuần 3+3+6 chia 3 nhánh, không phải môn/tín chỉ |
| 16 | 2026-10-05 | Người dùng là danh tính toàn cục, **thành viên theo từng tổ chức**; hồ sơ cá nhân thuộc về tổ chức | Một người có thể nộp vào nhiều trường mà dữ liệu không lẫn |
| 17 | 2026-10-05 | Phụ cấp chỉ **ghi nhận**, chi trả thực hiện ngoài hệ thống | Giảm rủi ro tài chính và phạm vi |
| 18 | 2026-10-05 | Giao diện **tiếng Việt mặc định, hỗ trợ tiếng Anh** | Đối tượng chính là người Việt; trường khác có thể cần tiếng Anh |

## Câu hỏi còn mở
- CRM của Northwind University/tập đoàn đối tác là gì? LMS: công khai cho thấy Northwind University dùng Canvas, cần xác nhận LMS dùng cho chương trình mẫu.
- Bài đánh giá năng lực vòng 2 chạy trên nền tảng nào; có cần engine làm bài tích hợp không?
- Danh sách đầy đủ ở [10-sample-tenant.md](10-sample-tenant.md) mục 6.
- Quy định dữ liệu cá nhân (Nghị định 13/2023/NĐ-CP): thời gian lưu trữ, consent, quyền xoá dữ liệu — cần xác nhận với bộ phận pháp chế.
- Rubric chấm điểm cụ thể cho từng vòng và hạn mức (quota) mỗi đợt.
