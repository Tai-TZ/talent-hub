# Research: nền tảng tham chiếu và bài học áp dụng

Ngày research: 2026-10-05. Nguồn là các trang sản phẩm và bài viết công khai; chưa dùng thử trực tiếp các sản phẩm này.

## 1. Quản lý tuyển sinh (Admissions CRM)

| Nền tảng | Điểm đáng học | Áp dụng vào Talent Hub |
|---|---|---|
| [Slate (Technolutions)](https://technolutions.com/admissions/application-management) | Form và portal cấu hình được; **Reader workflow** (xem, ghi chú, chấm hồ sơ trên một màn hình); quản lý "bin" (nhóm hồ sơ chờ xử lý); **decision processing có điều kiện tiên quyết**, phát hành quyết định theo lô | Màn hình reviewer một trang (hồ sơ + rubric + ghi chú); hàng đợi hồ sơ theo trạng thái; quyết định theo lô nhưng chỉ khi đã qua phê duyệt |
| Salesforce Education Cloud / TargetX | Rất tuỳ biến, hệ sinh thái tích hợp lớn nhưng tốn công cấu hình | Giữ lớp adapter CRM chung để đẩy dữ liệu sang CRM có sẵn thay vì tự làm CRM đầy đủ |
| Element451 | Có AI trợ lý và tự động hoá giao tiếp với ứng viên | Chatbot giải đáp quy trình; thông báo tự động theo mốc trạng thái |

**Bài học:** tách rõ *đọc/chấm hồ sơ* (reviewer) với *ra quyết định* (approver); luôn có timeline minh bạch cho ứng viên; mọi tự động hoá phải cấu hình được theo đợt tuyển.

## 2. Đánh giá chuẩn đầu ra (Learning Outcomes Assessment)

| Nền tảng | Điểm đáng học | Áp dụng |
|---|---|---|
| [Watermark (Taskstream, Tk20, LiveText)](https://watermarkinsights.com/solutions/outcomes-assessment-software/) | Gắn kết chương trình với chuẩn đầu ra (curriculum mapping); đánh giá theo rubric; **Planning & Self-Study** theo dõi chuẩn đầu ra được đánh giá ở đâu, phát hiện khoảng trống chương trình và theo dõi hiệu quả hành động cải tiến | Ma trận chuẩn đầu ra ↔ bài đánh giá; cảnh báo chuẩn đầu ra không có bài nào đo; vòng đời "đề xuất cải tiến → theo dõi hiệu quả" |
| Canvas Outcomes / Anthology | Điểm từ LMS được map về outcome, tính mastery | Đồng bộ điểm từ LMS qua adapter và tính attainment trong Talent Hub |

**Bài học:** chuẩn đầu ra là trung tâm; cần cả góc nhìn *cá nhân học viên* lẫn *cấp chương trình*, và cải tiến phải là một vòng lặp có theo dõi, không chỉ là báo cáo một lần.

## 3. RAG có trích nguồn

Tổng hợp từ các bài hướng dẫn công khai (ví dụ [Supermemory](https://blog.supermemory.ai/how-to-build-rag-based-chatbot-guide)):
- **Hybrid search** (vector + từ khoá) tốt hơn từng loại riêng; thường trọng số khoảng 70/30 vector/BM25.
- **Rerank** top 50 xuống top 5 giúp giảm bỏ sót, đổi lại thêm khoảng 150ms.
- **Grounding gate**: prompt bắt buộc trích nguồn, kiểm tra citation, mặc định từ chối khi thiếu ngữ cảnh.
- Đánh giá ở 3 tầng: retrieval (precision/recall/MRR), generation (hallucination rate), end-to-end.
- pgvector đủ dùng khi dưới ~10M vector.

**Áp dụng:** dùng pgvector + full-text của Postgres, rerank là bước tuỳ chọn qua adapter, bắt buộc có bộ câu hỏi kiểm thử (eval set) trước khi bật cho người dùng.

## 4. Đăng nhập Microsoft: bài học bảo mật nOAuth

Theo [Semperis](https://www.semperis.com/blog/noauth-abuse-alert-full-account-takeover/) và [hướng dẫn của Microsoft](https://learn.microsoft.com/et-EE/azure/active-directory/develop/migrate-off-email-claim-authorization): claim `email` trong ID token của Entra ID **không được xác minh**; kẻ tấn công tạo tenant riêng với email trùng email nạn nhân là chiếm được tài khoản nếu app định danh người dùng bằng email. MFA và Conditional Access không chặn được.

**Áp dụng (thay đổi so với thiết kế trước):**
- Định danh duy nhất bằng cặp **`iss` + `sub`** (hoặc `tid` + `oid`), không dùng email để tìm hay gộp tài khoản.
- **Nhân sự**: admin tạo user, hệ thống gửi link mời một lần; người dùng đăng nhập Microsoft qua link đó để *gắn* `tid+oid` vào user. Sau đó mới đăng nhập bằng Microsoft được. Không có bước nào tự gắn theo email.
- **Ứng viên**: đăng nhập Microsoft lần đầu tạo user `applicant` mới, định danh bằng `iss+sub`. Email chỉ lưu để liên lạc và được xác minh riêng bằng link gửi về email.
- Cấu hình danh sách tenant được phép cho nhân sự (`MS_STAFF_TENANT_IDS`).

## 5. AI trong xét tuyển: quản trị và tuân thủ

Theo các phân tích về [EU AI Act](https://www.ehu.eus/en/web/adimen-artifiziala/qu%C3%A9-implica-que-un-uso-sea-de-especial-sensibilidad) và [luật tuyển sinh AI ở Mỹ](https://gradpilot.com/news/ai-admissions-laws-colorado-california-2027), AI dùng để quyết định tuyển sinh thường được coi là rủi ro cao. Yêu cầu chung: giám sát của con người, minh bạch với ứng viên, giải thích được, kiểm soát thiên lệch, có đường khiếu nại tới người thật.

**Áp dụng:**
- AI chỉ gợi ý, không đổi trạng thái (đã chốt ở quyết định #11).
- Thông báo cho ứng viên khi nộp hồ sơ nếu đợt tuyển bật AI chấm sơ bộ; ứng viên có thể yêu cầu xem xét lại bởi người.
- Mỗi gợi ý AI lưu model, phiên bản prompt, lý do dạng văn bản; reviewer thấy nhưng không bị điểm AI áp đặt (ẩn điểm AI cho đến khi reviewer chấm xong, để tránh neo).
- Không đưa thuộc tính nhạy cảm (giới tính, dân tộc, tôn giáo, địa chỉ chi tiết, ảnh) vào prompt chấm điểm.
- Báo cáo công bằng định kỳ: so sánh tỉ lệ đạt theo nhóm (khi có dữ liệu được phép thu thập hợp pháp).
- Dữ liệu cá nhân: tuân thủ Nghị định 13/2023/NĐ-CP (consent, mục đích, quyền truy cập và xoá); cần pháp chế xác nhận thời hạn lưu trữ.
