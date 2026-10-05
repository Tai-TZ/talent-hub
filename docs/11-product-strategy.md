# Chiến lược sản phẩm: USP, moat và các khoảnh khắc WOW

Tài liệu này trả lời câu hỏi "tại sao sản phẩm này đáng được nhớ và đáng đầu tư", làm cơ sở chọn tính năng. Số liệu trích từ nguồn công khai; mọi thứ còn lại ghi rõ là giả định cần kiểm chứng.

## 1. Vấn đề thật sự

Một chương trình đào tạo nhân tài AI quy mô lớn ([chương trình mẫu](10-sample-tenant.md)) chạy **nhiều khoá liên tiếp**, mỗi khoá khoảng 500 học viên chọn ra từ hàng nghìn hồ sơ, 12 tuần, thực chiến tại doanh nghiệp đối tác, theo dõi kết quả việc làm. Điều này tạo ra bốn nỗi đau mà bảng tính và CRM tuyển sinh thông thường không giải quyết:

| # | Nỗi đau | Ai chịu | Hậu quả |
|---|---|---|---|
| 1 | **Đọc hàng nghìn hồ sơ trong vài ngày**; reviewer mệt, chấm lệch nhau, dễ bị "neo" bởi điểm hoặc lời nhận xét của người khác | Ban tuyển sinh, reviewer | Chọn sai người, thiếu nhất quán, khó giải trình khi bị khiếu nại |
| 2 | **Không biết tiêu chí tuyển chọn có dự đoán được thành công hay không**: 127 học viên chưa đạt ở khoá 1 liệu có dấu hiệu từ lúc tuyển? | Ban điều hành chương trình | Mỗi khoá lặp lại cùng một cách chọn mà không học được gì |
| 3 | **Xếp lớp, chia nhánh, ghép đối tác thực chiến bằng tay** với nhiều ràng buộc (trình độ, nguyện vọng, sức chứa, nhu cầu đối tác) | Quản lý khoá học | Lớp mất cân bằng, học viên không đúng chỗ, tốn nhiều ngày công |
| 4 | **Không chứng minh được kết quả**: nhà tài trợ, đối tác và báo chí hỏi "bao nhiêu người thật sự đạt, tốn bao nhiêu tiền cho mỗi người". Báo cáo kết quả của ngành bootcamp từng bị nghi ngờ phóng đại, nên chuẩn như [CIRR](https://www.cirr.org/for-students) yêu cầu báo cáo có kiểm chứng (việc làm sau 90 và 180 ngày) | Nhà tài trợ, lãnh đạo | Khó gọi thêm vốn, khó mở rộng |

Thêm áp lực pháp lý: AI dùng để xét tuyển thường bị coi là rủi ro cao, cần giám sát của con người, giải thích được và kiểm soát thiên lệch ([03-research.md](03-research.md)).

## 2. Đối thủ và khoảng trống

| Nhóm | Ví dụ | Mạnh | Không làm |
|---|---|---|---|
| CRM/quy trình tuyển sinh | [Slate](https://technolutions.com/admissions/application-management), Salesforce Education Cloud, Element451 | Quy trình đọc hồ sơ, quyết định theo lô, tích hợp | Không nối **tuyển chọn → kết quả đào tạo → việc làm**; AI chỉ ở mức chatbot hoặc tự động hoá giao tiếp |
| Công cụ đánh giá/ phỏng vấn | Kira Talent (video, chấm điểm, phát hiện thiên lệch) | Phỏng vấn video, người chấm | Không học từ kết quả sau tuyển sinh |
| Công cụ trích xuất | Sia/Airr (bảng điểm) | Trích dữ liệu bảng điểm | Một khâu rất hẹp |
| ATS tuyển dụng | Greenhouse, Ashby, Eightfold, HireVue | Quy trình tuyển dụng, một số có kiểm toán thiên lệch theo quy định NYC LL144 | Thiết kế cho tuyển nhân sự, không cho **khoá học theo đợt có đào tạo và xếp lớp**; Greenhouse cố ý tránh ML |
| LMS / nền tảng outcomes | Canvas, Watermark | Điểm, chuẩn đầu ra | Không thấy giai đoạn tuyển sinh và thực chiến |
| Nền tảng bootcamp | Disco, các nền tảng khoá theo nhóm | Quản lý khoá, tiến độ | Không có AI sàng lọc có bằng chứng, không có vòng học từ kết quả |

**Khoảng trống thật:** chưa có sản phẩm nào khép kín vòng **Chọn → Xếp → Đào tạo → Đánh giá → Việc làm → quay lại cải tiến cách chọn**, kèm AI có bằng chứng kiểm chứng được và kiểm soát công bằng. Đó là nơi đặt USP.

## 3. USP và moat

> **Talent Hub là hệ điều hành "từ tuyển chọn đến kết quả" cho chương trình đào tạo nhân tài theo đợt: AI đọc hồ sơ có dẫn chứng kiểm chứng được, con người quyết định, và hệ thống tự học từ kết quả để chọn tốt hơn ở khoá sau.**

| Moat | Vì sao khó sao chép |
|---|---|
| **Dữ liệu dọc tích luỹ** (tín hiệu lúc tuyển ↔ năng lực lúc học ↔ việc làm) | Mỗi khoá chạy thêm là dữ liệu và mô hình tốt hơn; đối thủ chỉ nắm một khâu. Qua nhiều trường có thể đối sánh ẩn danh |
| **AI có bằng chứng được kiểm chứng ở server**: mọi trích dẫn phải xuất hiện nguyên văn trong hồ sơ, không thì bị loại | Chống "AI bịa", đáp ứng yêu cầu giải thích; cần thiết kế kỹ thuật chứ không chỉ prompt |
| **Quy trình chống thiên lệch nhận thức đưa vào luồng**: chấm mù, AI chỉ hiện sau khi reviewer chốt điểm, giám sát công bằng liên tục | Là thiết kế quy trình + dữ liệu, gắn vào thói quen người dùng |
| **Bộ giải xếp lớp/ghép đối tác có giải thích** | Có chiều sâu thuật toán và ràng buộc nghiệp vụ riêng |
| **Hồ sơ năng lực có chữ ký (Skill Passport)** chuẩn hoá theo SFIA, dạng [Open Badges 3.0](https://anonyome.com/?p=9276) (W3C Verifiable Credential) | Học viên và đối tác tự muốn dùng: hiệu ứng mạng lưới |

## 4. Ba khoảnh khắc WOW dành cho buổi pitching

Mỗi cái đều chạy thật trên dữ liệu, có giá trị kinh doanh rõ ràng, không dựa vào hiệu ứng hình ảnh.

### WOW 1 — "1.000 hồ sơ, 60 giây, mỗi điểm đều có dẫn chứng" (AI Screening Copilot)
- Bấm một nút: hệ thống phân loại cả đợt thành **Nên mời / Cần xem / Khả năng loại**, mỗi hồ sơ kèm điểm theo rubric, **đoạn trích nguyên văn làm bằng chứng được tô sáng**, các điểm cần xác minh và độ tin cậy.
- Reviewer dồn thời gian vào nhóm "Cần xem" (vùng AI không chắc). Chế độ **chấm mù** ẩn danh tính; điểm AI chỉ hiện **sau** khi reviewer chốt điểm của mình.
- Giá trị: thời gian xử lý mỗi đợt giảm mạnh, chất lượng nhất quán, có chứng cứ khi bị khiếu nại. Với nhà đầu tư: đây là phần tự động hoá việc nặng nhất của chương trình.

### WOW 2 — "Rubric Lab: đặt lại luật chơi bằng dữ liệu" (Selection-to-Success)
- Hệ thống xem lại các khoá đã chạy: **tiêu chí nào thật sự dự đoán học viên đạt yêu cầu và có việc làm** (hệ số, khoảng tin cậy, cỡ mẫu, cảnh báo khi dữ liệu ít).
- Kéo thanh trượt đổi trọng số, hệ thống **chạy lại xếp hạng của khoá trước**: ai sẽ được chọn khác đi, tỉ lệ đạt dự kiến thay đổi bao nhiêu, và **kiểm tra tác động công bằng ngay lập tức**.
- Giá trị: biến tuyển sinh từ cảm tính thành vòng cải tiến liên tục. Đây là lợi thế dữ liệu mà đối thủ không có.

### WOW 3 — "Cohort Composer: một cú bấm xếp xong lớp và vị trí thực chiến"
- Bộ giải xếp học viên vào lớp theo trình độ, vào nhánh theo năng lực và nguyện vọng, vào vị trí đối tác theo nhu cầu và sức chứa; cho phép đặt ràng buộc (cân bằng nền tảng, tối thiểu mỗi lớp), xem **lý do từng quyết định** và so sánh phương án.
- Giá trị: thay nhiều ngày làm tay, giảm sai lệch, minh bạch với đối tác.

### Hỗ trợ cho câu chuyện gọi vốn
- **Bảng điều khiển chi phí** cho IT và tài chính: chi phí AI, phụ cấp, chi phí mỗi học viên đạt yêu cầu (**cost per qualified engineer**), cảnh báo vượt ngân sách.
- **Giám sát công bằng và gói kiểm toán**: tỉ lệ tác động tới từng nhóm (quy tắc bốn phần năm), nhật ký con người duyệt, xuất báo cáo cho nhà tài trợ và cơ quan quản lý.
- **Cổng ứng viên minh bạch**: thấy đang ở bước nào, thiếu gì, vì sao; trợ lý trả lời có trích nguồn.

## 5. Mô hình kinh doanh (giả thuyết cần kiểm chứng)

| Dòng thu | Cách tính | Lý do |
|---|---|---|
| Phí nền tảng theo chương trình/khoá | Cố định theo khoá hoặc theo quy mô tuyển | Dễ ngân sách hoá cho trường và nhà tài trợ |
| Phí theo ứng viên được sàng lọc bằng AI | Theo số hồ sơ xử lý, hoàn lại một phần chi phí LLM | Gắn với giá trị tiết kiệm được |
| Gói kiểm toán và báo cáo kết quả | Theo năm | Nhà tài trợ cần số liệu có thể kiểm chứng |
| Mạng lưới Skill Passport cho đối tác tuyển dụng | Theo lượt truy cập hoặc gói đối tác | Hiệu ứng mạng lưới về sau |

Quy mô thị trường: **cần nghiên cứu thêm**, không đưa số chưa kiểm chứng vào tài liệu pitching.

## 6. Thứ tự ưu tiên xây dựng

1. **Nền tảng nghiệp vụ**: đợt tuyển, hồ sơ, rubric, vòng xét, phê duyệt hai cấp, nhập học (không có thì các WOW không có chỗ đứng).
2. **WOW 1**: động cơ sàng lọc có bằng chứng (offline bằng luật và từ vựng; nâng cấp bằng LLM khi có khoá API), bảng phân loại, chấm mù, chống neo.
3. **Trang Admin cho IT**: người dùng, cấp tài khoản, tài liệu, chi phí, cấu hình, nhật ký.
4. **WOW 3**: Cohort Composer.
5. **WOW 2**: Rubric Lab (cần dữ liệu lịch sử; demo bằng dữ liệu tổng hợp gắn nhãn rõ ràng).
6. Công bằng, kiểm toán, Skill Passport, cổng minh bạch, trợ lý RAG.

## 7. Trung thực về dữ liệu demo

Chương trình thật chưa cung cấp hồ sơ ứng viên, rubric hay kết quả chi tiết. Để demo, hệ thống có bộ sinh dữ liệu **tổng hợp** (ứng viên giả, ba khoá lịch sử và một đợt đang tuyển), luôn hiển thị nhãn "Dữ liệu minh hoạ". Thuật toán chạy thật; con số kết quả trên dữ liệu minh hoạ **không** phải kết quả của một tổ chức thật và không dùng làm bằng chứng hiệu quả khi pitching.

## 8. Đo thành công (giả thuyết cần đo)

| Chỉ số | Cách đo |
|---|---|
| Thời gian xử lý hồ sơ trên mỗi reviewer | So sánh có và không có triage |
| Mức đồng thuận giữa các reviewer | Kappa/Krippendorff trước và sau |
| Tỉ lệ AI gợi ý bị reviewer đổi | Theo tiêu chí và theo nhóm |
| Độ chính xác dự đoán đạt yêu cầu từ tín hiệu tuyển chọn | AUC trên khoá giữ lại |
| Chênh lệch công bằng giữa các nhóm | Tỉ lệ tác động |
| Chi phí mỗi học viên đạt yêu cầu | Tổng chi phí chia số đạt |
