# Đa tổ chức (multi-tenancy): Northwind University trước, các trường khác sau

**Mục tiêu:** Northwind University là tổ chức đầu tiên và quyết định các tính năng cụ thể; mọi thứ riêng của Northwind University phải nằm trong **cấu hình**, không nằm trong code, để thêm một trường mới (hoặc một chương trình khác của chính Northwind University) chỉ cần tạo tổ chức mới và nạp cấu hình.

## 1. Ranh giới: cái gì chung, cái gì riêng

| Chung cho mọi tổ chức (code) | Riêng cho từng tổ chức (cấu hình/dữ liệu) |
|---|---|
| State machine hồ sơ, kiểm tra quyền, audit | Dãy vòng xét tuyển, rubric, form hồ sơ, có/không phê duyệt 2 cấp |
| Engine tính attainment, rule cảnh báo | Khung năng lực/chuẩn đầu ra (SFIA, PLO, ABET…), ngưỡng, quy tắc xét đạt |
| Pipeline RAG, lớp provider LLM | Kho tri thức, prompt bổ sung, provider/model, quota |
| Lớp connector CRM/LMS | Loại và thông tin kết nối CRM/LMS |
| Đăng nhập OIDC | Nhà cung cấp danh tính, tenant Microsoft được phép, miền email |
| Giao diện | Logo, màu, ngôn ngữ mặc định (vi/en), múi giờ, mẫu email |
| Cấu trúc chương trình: Program → Cohort → Phase → Track | Số phase, độ dài, tên, track cụ thể của từng chương trình |

## 2. Mô hình cô lập dữ liệu

Chọn **một database, một schema dùng chung, cột `organization_id` + Row-Level Security (RLS)**. Lý do: [các hướng dẫn thực hành](https://makerkit.dev/blog/tutorials/multi-tenant-saas-architecture) đều khuyến nghị mức chia sẻ cao nhất mà yêu cầu cho phép, vì mỗi bước tăng cô lập nhân thêm công vận hành (migration N lần, kết nối khó quản lý khi nhiều tổ chức). Schema-per-tenant chỉ hợp lý khoảng vài trăm tổ chức trở lại; database-per-tenant dành cho hợp đồng yêu cầu cô lập tuyệt đối và có thể thêm sau mà không đổi code ứng dụng (chỉ đổi chuỗi kết nối theo tổ chức).

Quy tắc bắt buộc (theo các cạm bẫy phổ biến của RLS với [FastAPI/SQLAlchemy](https://fastapi-tenancy.readthedocs.io/en/latest/guides/isolation/rls/)):

1. **Mọi bảng thuộc về tổ chức** có `organization_id uuid NOT NULL`, khoá ngoại tới `organizations`, và policy:
   ```sql
   ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
   ALTER TABLE applications FORCE ROW LEVEL SECURITY;
   CREATE POLICY org_isolation ON applications
     USING (organization_id = current_setting('app.org_id', true)::uuid)
     WITH CHECK (organization_id = current_setting('app.org_id', true)::uuid);
   ```
2. **Vai trò DB của ứng dụng không phải superuser, không có `BYPASSRLS`, không sở hữu bảng** (migration chạy bằng vai trò chủ sở hữu riêng). Có test khởi động kiểm tra điều này và dừng app nếu sai.
3. Ngữ cảnh đặt bằng `SET LOCAL app.org_id = ...` (qua `set_config(..., true)`) **ngay đầu transaction** của mỗi request, nên tự mất khi commit/rollback và không rò rỉ giữa các request dùng chung kết nối. Thiếu ngữ cảnh thì `current_setting` trả null và policy không khớp dòng nào (an toàn theo mặc định).
4. Ràng buộc duy nhất luôn gồm `organization_id` (ví dụ `UNIQUE(organization_id, code)`); khoá ngoại giữa các bảng dùng khoá kép `(organization_id, id)` ở chỗ nhạy cảm để không thể trỏ chéo tổ chức.
5. Worker và job định kỳ: payload luôn có `organization_id`; wrapper đặt ngữ cảnh trước khi chạy. Job quét toàn hệ thống lặp qua từng tổ chức, mỗi tổ chức một transaction.
6. Lưu trữ file: khoá object bắt đầu bằng `org/{organization_id}/...`; presigned URL chỉ cấp sau khi kiểm tra quyền trong ngữ cảnh tổ chức.
7. Vector/RAG: `kb_chunks.organization_id` bắt buộc, lọc theo tổ chức trước khi xếp hạng; chỉ mục HNSW toàn cục ở giai đoạn đầu (chuyển sang phân vùng theo tổ chức nếu số vector lớn).
8. Cache (Redis) và khoá giới hạn tốc độ có tiền tố `org:{id}:`.
9. **Test cô lập bắt buộc trong CI:** tạo 2 tổ chức, với mỗi bảng thuộc về tổ chức thử đọc/ghi/sửa/xoá chéo qua cả API lẫn SQL trực tiếp bằng vai trò ứng dụng; bất kỳ bảng nào có `organization_id` mà thiếu policy sẽ làm test fail (kiểm tra tự động bằng `pg_policies`).

## 3. Xác định tổ chức của request

- Môi trường thật: tên miền con `northwind.<domain>` (hoặc tên miền riêng cho từng trường); môi trường local: header `X-Organization: northwind`.
- Token đăng nhập chứa `org_id`; API kiểm tra tổ chức từ tên miền **trùng** với tổ chức trong token và người dùng còn là thành viên (`org_memberships.status = active`), nếu không trả `403`.
- Ngoại lệ có kiểm soát: vai trò `platform_admin` (vận hành nền tảng, thuộc tổ chức hệ thống) dùng vai trò DB riêng được phép đặt ngữ cảnh sang tổ chức khác; mọi thao tác ghi audit kèm lý do và tổ chức đích.

## 4. Người dùng thuộc nhiều tổ chức

- `users` là danh tính toàn cục (email, định danh Microsoft `iss+sub`); `org_memberships` gắn người dùng với từng tổ chức, `user_roles` thuộc về membership.
- Một ứng viên nộp hồ sơ vào hai trường chỉ có hai membership `applicant`; **hồ sơ cá nhân (`applicant_profiles`), tài liệu, consent thuộc về tổ chức** nên trường này không thấy dữ liệu của trường kia.
- Nhân sự một trường không tự thấy tổ chức khác; được mời riêng cho từng tổ chức.

## 5. Cấu hình theo tổ chức

| Bảng | Nội dung |
|---|---|
| `organizations` | `slug`, `name`, `default_locale`, `timezone`, `branding` (logo, màu), `status`, `plan_limits` (số hồ sơ, dung lượng, quota LLM) |
| `org_settings` | cặp khoá/giá trị JSON có schema kiểm tra: ngôn ngữ, mẫu email, chính sách retention, bật/tắt tính năng AI |
| `org_idp_connections` | `type` (`microsoft` mặc định, `oidc` chung), `issuer`, `client_id`, `client_secret` (mã hoá), `allowed_tenant_ids`, `staff_email_domains` |
| `org_llm_settings` | provider/model theo tác vụ; khoá API riêng của tổ chức (tuỳ chọn, mã hoá bằng khoá chủ trong biến môi trường); nếu không có thì dùng khoá hệ thống và tính vào quota |
| `program_templates` | mẫu cấu hình có phiên bản (xem mục 6) |

## 6. Mẫu chương trình (program template)

Một tệp JSON/YAML mô tả toàn bộ phần đặc thù của một chương trình, được kiểm tra bằng JSON Schema và nạp bằng CLI hoặc màn hình admin:

```yaml
program:  { code: ai-talent, name: {vi: ..., en: ...} }
phases:   [ {key: foundation, weeks: 3}, {key: simulation, weeks: 3}, {key: placement, weeks: 6} ]
tracks:   [ ai_products, ai_infrastructure, ai_applications ]
framework: { type: sfia, version: 9, scale: level, targets_by_track: {...} }
intake:
  rounds: [ {key: portfolio, type: review, rubric: ...}, {key: aptitude, type: assessment, rubric: ...} ]
  approval: two_level          # hoặc: single_level, none
  after_accept: [ assign_track, enroll ]
  form_schema: {...}
qualification: { rule: ... }   # điều kiện được công nhận hoàn thành
stipend: { amount_vnd: 8000000, period: month, conditions: [...] }
```

Thêm một trường mới nghĩa là viết một mẫu mới (ví dụ chương trình cử nhân với học kỳ, môn, PLO tính theo điểm phần trăm) mà không sửa code. Những gì mẫu chưa diễn tả được thì mới phải bổ sung vào engine, và bổ sung theo hướng tổng quát.

## 7. Chuẩn bị cho quy mô

Giả định thiết kế (cần xác nhận với Northwind University): 10.000–20.000 học viên trong 2 năm, khoảng 500 học viên mỗi khoá, và mỗi khoá nhận hàng nghìn hồ sơ. Do đó:
- Hàng đợi hồ sơ phân trang bằng cursor, có chỉ mục `(organization_id, intake_id, status, current_round)`.
- Hành động hàng loạt (phân công, chuyển vòng, đề xuất, duyệt theo lô) chạy nền với tiến độ, mỗi hồ sơ vẫn tạo sự kiện và audit riêng.
- Luật sàng lọc tự động theo điều kiện đủ tư cách (ví dụ thiếu giấy tờ bắt buộc) giảm tải reviewer, nhưng chỉ **gợi ý loại** để người xác nhận hàng loạt, không tự loại.
- Số liệu nặng (funnel, attainment) dùng bảng tổng hợp cập nhật theo job thay vì quét bảng gốc mỗi lần mở dashboard.
- Mục tiêu hiệu năng ban đầu: danh sách hồ sơ p95 < 300 ms với 50.000 hồ sơ/tổ chức; đo bằng bộ dữ liệu giả lập sinh sẵn trong repo.

## 8. Vận hành một tổ chức mới

1. `platform_admin` chạy `python -m app.cli org create --slug <slug> --name "<tên>" --admin-email <email>`.
2. Cấu hình nhận diện, IdP, ngôn ngữ; nạp mẫu chương trình (`org template apply`).
3. Admin tổ chức nạp kho tri thức, mời nhân sự, mở đợt tuyển.
4. Xuất/xoá toàn bộ dữ liệu của một tổ chức bằng lệnh có xác nhận hai bước và audit (đáp ứng yêu cầu hợp đồng, quyền xoá dữ liệu).
