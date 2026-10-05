# Tích hợp: Power BI, LMS, CRM

Hệ thống bên ngoài gọi API tích hợp bằng **khoá API theo tổ chức** (Bearer). Admin tạo khoá ở **Quản trị › Tích hợp**, chọn phạm vi tối thiểu cần dùng. Khoá chỉ hiện **một lần** khi tạo (hệ thống chỉ lưu băm SHA-256); thu hồi là hết hiệu lực ngay. Mỗi khoá có một tài khoản dịch vụ riêng nên mọi thao tác qua khoá đều nằm trong nhật ký hoạt động với đúng tác nhân.

| Phạm vi | Dùng cho | Endpoint |
|---|---|---|
| `export.read` | Power BI, Excel, kho dữ liệu | `GET /api/v1/integrations/exports/{applications,enrollments,competency_attainment}.csv` |
| `lms.read` | LMS lấy danh sách học viên của khoá | `GET /api/v1/integrations/lms/roster?cohort=K3` |
| `lms.write` | LMS đẩy kết quả đánh giá năng lực | `POST /api/v1/integrations/lms/assessments` |
| `crm.read` | CRM đồng bộ ứng viên và trạng thái hồ sơ | `GET /api/v1/integrations/crm/applications?updated_since=…&cursor=…` |

Địa chỉ gốc là tên miền của tổ chức (ví dụ `https://northwind.talenthub.example`); tổ chức được xác định từ tên miền, khoá của tổ chức này không dùng được ở tổ chức khác (RLS).

## Power BI

Export CSV đã **khử định danh**: không có họ tên, email, số điện thoại; giới tính và khu vực là thông tin tự khai, chỉ dùng cho thống kê gộp (giám sát công bằng).

| Bộ dữ liệu | Một dòng là | Cột chính |
|---|---|---|
| `applications.csv` | một hồ sơ đã nộp | `candidate_code`, `intake_name`, `status`, `current_round`, `submitted_at`, `gender`, `region`, `ai_tier`, `ai_score` |
| `enrollments.csv` | một học viên trong khoá | `cohort_code`, `track`, `class`, `status`, `enrolled_at`, `qualification_decided_at` |
| `competency_attainment.csv` | một (học viên, năng lực mục tiêu) | `cohort_code`, `track`, `competency_code`, `target_level`, `latest_level`, `met`, `assessments` |

Kết nối trong Power BI Desktop: **Get data › Blank query › Advanced editor**, dán đoạn sau (thay địa chỉ và khoá), rồi **Close & Apply**. Lưu khoá trong tham số Power BI thay vì viết thẳng vào truy vấn khi chia sẻ báo cáo.

```powerquery
let
    BaseUrl = "https://northwind.talenthub.example",
    ApiKey = "thk_...",
    Load = (dataset as text) =>
        Csv.Document(
            Web.Contents(BaseUrl, [
                RelativePath = "/api/v1/integrations/exports/" & dataset & ".csv",
                Headers = [Authorization = "Bearer " & ApiKey]
            ]),
            [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
        ),
    Attainment = Table.PromoteHeaders(Load("competency_attainment"), [PromoteAllScalars = true])
in
    Attainment
```

Gợi ý dashboard: tỉ lệ `met` theo `competency_code` × `cohort_code` (chuẩn đầu ra theo khoá), phễu `status` theo `intake_name`, tỉ lệ được nhận theo `gender`/`region` (chỉ nhóm từ 20 người). Khi xuất bản lên Power BI Service, cấu hình làm mới định kỳ với thông tin xác thực "Anonymous" + header như trên.

## LMS

```bash
# Danh sách học viên của khoá K3 (để LMS tạo lớp/ghi danh)
curl -H "Authorization: Bearer $KEY" https://northwind.talenthub.example/api/v1/integrations/lms/roster?cohort=K3

# Đẩy kết quả đánh giá năng lực (tối đa 1.000 mục mỗi lần)
curl -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  https://northwind.talenthub.example/api/v1/integrations/lms/assessments \
  -d '{"items":[{"external_ref":"moodle-grade-8812","candidate_code":"NW-K3-0042","competency_code":"programming","level":5,"evidence":"Bài kiểm tra cuối học phần","assessed_at":"2026-10-01T09:00:00Z"}]}'
```

- `external_ref` là mã duy nhất phía LMS: gửi lại cùng mã sẽ được bỏ qua (`duplicates`), nên LMS có thể thử lại an toàn khi lỗi mạng.
- Phản hồi `{created, duplicates, errors[]}`; lỗi theo từng mục (`unknown_candidate`, `unknown_competency`, `level_out_of_range`) không làm hỏng cả lô.
- Đánh giá từ LMS đi vào cùng ma trận năng lực với đánh giá của mentor, nên xuất hiện ngay trong xét đạt và trang Chất lượng chương trình.

## CRM

```bash
curl -H "Authorization: Bearer $KEY" \
  "https://northwind.talenthub.example/api/v1/integrations/crm/applications?updated_since=2026-10-01T00:00:00Z&limit=200"
# Lặp lại với ?cursor=<next_cursor> cho đến khi next_cursor = null; lưu updated_at lớn nhất cho lần đồng bộ sau.
```

Trả về liên hệ (họ tên, email, điện thoại) và trạng thái hồ sơ, sắp theo `updated_at` (phân trang keyset, không bỏ sót khi có thay đổi trong lúc đọc). Vì có dữ liệu cá nhân, phạm vi `crm.read` tách riêng và mỗi lần đọc đều ghi nhật ký.
