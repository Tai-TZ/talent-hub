# Quyết định kiến trúc (ADR log)

| # | Ngày | Quyết định | Lý do |
|---|------|-----------|-------|
| 1 | 2026-10-05 | Mục tiêu: **sản phẩm thật** | Cần bảo mật, audit log, khả năng scale, tích hợp CRM/LMS thực tế |
| 2 | 2026-10-05 | Backend: **FastAPI (Python)** | Thuận tiện cho LLM/RAG và phân tích dữ liệu |
| 3 | 2026-10-05 | Frontend: **Next.js (React, TypeScript)** | Theo gợi ý đề bài |
| 4 | 2026-10-05 | Database: **PostgreSQL + pgvector** | Một DB cho dữ liệu nghiệp vụ và vector RAG |
| 5 | 2026-10-05 | LLM: **lớp adapter đa provider**, gắn API key sau | Không khoá cứng vào một provider; đổi qua cấu hình |
| 6 | 2026-10-05 | Dashboard: **built-in (web) + export dataset cho Power BI** | Vận hành hằng ngày trên web; báo cáo quản lý qua Power BI |

## Câu hỏi còn mở
- CRM/LMS cụ thể sẽ tích hợp là gì (HubSpot, Salesforce, Moodle, Canvas, hệ thống nội bộ...)?
- Đăng nhập: email/password, Google, hay SSO của tổ chức?
- Cloud đích: AWS, Azure, GCP hay VPS?
- Quy định dữ liệu cá nhân (Nghị định 13/2023/NĐ-CP): thời gian lưu trữ, consent, quyền xoá dữ liệu.
