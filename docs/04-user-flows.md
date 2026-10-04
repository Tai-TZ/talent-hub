# Màn hình và luồng người dùng

## 1. Bản đồ màn hình

| Khu vực | Đường dẫn | Vai trò | Nội dung |
|---|---|---|---|
| Đăng nhập | `/login` | tất cả | Email + mật khẩu, nút Microsoft |
| Đặt mật khẩu / nhận lời mời | `/invite/[token]` | nhân sự mới | Đặt mật khẩu hoặc gắn tài khoản Microsoft |
| Cổng ứng viên | `/apply` | applicant | Danh sách đợt tuyển đang mở, hồ sơ của tôi |
| Form hồ sơ | `/apply/[applicationId]` | applicant | Nhiều bước: thông tin, học vấn, kinh nghiệm, tài liệu, cam kết và consent |
| Timeline hồ sơ | `/apply/[applicationId]/status` | applicant | Trạng thái hiện tại, các mốc, yêu cầu bổ sung |
| Trợ lý AI | `/assistant` (và nút nổi) | tất cả | Hỏi đáp có trích nguồn |
| Hàng đợi hồ sơ | `/staff/applications` | reviewer, approver, admin | Lọc theo đợt, trạng thái, người phụ trách |
| Chi tiết hồ sơ | `/staff/applications/[id]` | reviewer, approver | Xem hồ sơ, chấm rubric, ghi chú, gợi ý AI, đề xuất |
| Hàng đợi phê duyệt | `/staff/approvals` | approver | Các đề xuất chờ duyệt, duyệt/trả lại |
| Dashboard tuyển sinh | `/staff/dashboard/admissions` | reviewer, approver, admin | Funnel, thời gian xử lý, tải reviewer |
| Chương trình đào tạo | `/training/programs` | training_manager | Chương trình, môn, chuẩn đầu ra, ma trận map |
| Dashboard đào tạo | `/training/dashboard` | training_manager | Attainment theo chuẩn đầu ra/khoá/môn |
| Cảnh báo dữ liệu | `/training/alerts` | training_manager | Danh sách cảnh báo, nhận xử lý, đóng |
| Báo cáo cải tiến | `/training/reports` | training_manager | Bản nháp do AI soạn, duyệt, theo dõi hành động |
| Quản trị | `/admin/*` | admin | Người dùng, đợt tuyển, rubric, kho tri thức, tích hợp, nhật ký audit |

## 2. Luồng ứng viên

1. Đăng nhập bằng Microsoft (hoặc tài khoản được cấp) → xác minh email nếu chưa xác minh.
2. Chọn đợt tuyển đang mở → tạo hồ sơ `DRAFT`. Hệ thống tự lưu nháp mỗi bước.
3. Điền form nhiều bước, tải tài liệu (CV, bảng điểm, chứng chỉ). Mỗi tài liệu hiển thị trạng thái quét và kiểm tra định dạng.
4. Bước cuối: đọc và tích consent (xử lý dữ liệu cá nhân; nếu đợt bật AI thì có thông báo AI hỗ trợ sàng lọc và quyền yêu cầu xem xét bởi người) → **Nộp**. Sau khi nộp không sửa được trừ khi trạng thái `NEEDS_INFO`.
5. Theo dõi timeline; nhận email mỗi khi đổi trạng thái chính hoặc cần bổ sung. Khi `NEEDS_INFO` thấy rõ danh sách thiếu và hạn bổ sung.
6. Có thể **rút hồ sơ** bất kỳ lúc nào trước quyết định.
7. Sau quyết định: xem kết quả, lý do (do reviewer/approver soạn cho ứng viên), nút **yêu cầu xem xét lại** (tạo ticket cho admin).

## 3. Luồng reviewer

1. Vào hàng đợi, lọc hồ sơ được phân công ở `SCREENING`/`TESTING`/`INTERVIEW`.
2. Mở chi tiết: cột trái là hồ sơ và tài liệu, cột phải là rubric, ô ghi chú, lịch sử.
3. Chấm từng tiêu chí rubric (thang điểm + nhận xét bắt buộc với điểm cực trị). Gợi ý AI chỉ hiện **sau khi** reviewer lưu điểm của mình.
4. Chọn hành động: yêu cầu bổ sung (`NEEDS_INFO`), chuyển vòng tiếp theo, hoặc **đề xuất** đỗ/loại/chờ kèm lý do → hồ sơ sang `PENDING_APPROVAL`.
5. Xung đột lợi ích: reviewer có thể khai báo "không thể chấm hồ sơ này", hệ thống trả lại cho admin phân công lại.

## 4. Luồng approver

1. Vào hàng đợi phê duyệt, xem đề xuất, tổng hợp điểm các reviewer, gợi ý AI và lý do.
2. Chọn **Duyệt** (đỗ/loại/chờ), **Trả lại** (kèm yêu cầu), không được duyệt đề xuất do chính mình tạo.
3. Có thể duyệt theo lô cho các đề xuất cùng loại, mỗi hồ sơ vẫn tạo bản ghi quyết định và audit riêng.
4. Quyết định có hiệu lực → worker gửi email cho ứng viên và đồng bộ CRM.

## 5. Luồng training manager

1. Khai báo chương trình, môn học, chuẩn đầu ra, ma trận bài đánh giá ↔ chuẩn đầu ra (kèm trọng số).
2. Cấu hình kết nối LMS; xem lịch sử đồng bộ và lỗi.
3. Xem dashboard attainment; bấm vào chuẩn đầu ra để xem môn/bài đóng góp, phân bố điểm, xu hướng theo khoá.
4. Xử lý cảnh báo: nhận xử lý → ghi chú → đóng (hoặc đánh dấu "không phải vấn đề").
5. Yêu cầu hệ thống soạn **báo cáo cải tiến** từ số liệu → chỉnh sửa → duyệt → tạo các hành động cải tiến có người phụ trách và hạn; theo dõi kết quả ở kỳ sau.

## 6. Luồng admin

1. Tạo/nhập người dùng, gán vai trò, gửi lời mời, khoá/mở khoá, reset mật khẩu.
2. Tạo đợt tuyển: thời gian, chỉ tiêu, các vòng, rubric, bật/tắt AI chấm sơ bộ, mẫu email.
3. Phân công reviewer (thủ công hoặc chia đều theo tải).
4. Quản lý kho tri thức cho trợ lý: upload tài liệu, chọn phạm vi `public`/`internal`, xem trạng thái xử lý, gỡ tài liệu.
5. Xem nhật ký audit, tải export dataset cho Power BI.

## 7. Thông báo

| Sự kiện | Người nhận | Kênh |
|---|---|---|
| Nộp hồ sơ thành công | Ứng viên | Email |
| Cần bổ sung | Ứng viên | Email + trong app |
| Đổi vòng | Ứng viên | Email |
| Có hồ sơ mới được phân công | Reviewer | Trong app (email gộp theo ngày) |
| Có đề xuất chờ duyệt | Approver | Trong app + email |
| Quyết định cuối | Ứng viên | Email |
| Cảnh báo dữ liệu mức cao | Training manager | Email |
