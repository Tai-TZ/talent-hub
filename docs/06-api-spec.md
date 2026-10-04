# Đặc tả API (v1)

Tiền tố `/api/v1`. JSON, UTF-8, thời gian ISO 8601 UTC. Lỗi theo RFC 9457 (`application/problem+json`) với `type`, `title`, `status`, `detail`, `request_id`. Phân trang bằng `?limit=&cursor=`. Tài liệu OpenAPI sinh tự động tại `/docs`.

**Tổ chức (tenant):** mọi request thuộc về đúng một tổ chức, xác định từ tên miền con (`northwind.<domain>`) hoặc header `X-Organization` ở môi trường local, và phải khớp `org_id` trong token cùng membership còn hiệu lực, nếu không trả `403`. Các endpoint bên dưới luôn chạy trong ngữ cảnh một tổ chức (RLS), trừ nhóm "Nền tảng". Chi tiết: [09-multi-tenancy.md](09-multi-tenancy.md).

Cột **Quyền** là permission cần có (xem bảng permission ở cuối). `own` nghĩa là chỉ trên dữ liệu của chính người gọi.

## Auth
| Method | Path | Mô tả | Quyền |
|---|---|---|---|
| POST | `/auth/login` | Email + mật khẩu → set cookie | public |
| POST | `/auth/logout` | Thu hồi refresh token | đã đăng nhập |
| POST | `/auth/refresh` | Xoay refresh token | cookie |
| GET | `/auth/microsoft/start` | Redirect sang Microsoft (state, nonce, PKCE) | public |
| GET | `/auth/microsoft/callback` | Xử lý code, tạo session | public |
| POST | `/auth/invitations/accept` | Đặt mật khẩu hoặc gắn Microsoft qua token mời | token |
| POST | `/auth/password/change` | Đổi mật khẩu | đã đăng nhập |
| POST | `/auth/email/verify` | Xác minh email bằng token | token |
| GET | `/me` | Thông tin và permission của tôi | đã đăng nhập |

## Admin: người dùng, đợt tuyển
| Method | Path | Mô tả | Quyền |
|---|---|---|---|
| GET/POST | `/admin/users` | Danh sách / tạo user (gửi lời mời) | `user.manage` |
| POST | `/admin/users/import` | Import CSV | `user.manage` |
| PATCH | `/admin/users/{id}` | Sửa, khoá, đổi vai trò | `user.manage` |
| POST | `/admin/users/{id}/reset-password` | Gửi lại lời mời | `user.manage` |
| GET/POST | `/intakes` | Danh sách / tạo đợt (GET mở cho applicant, chỉ đợt `open`) | `intake.read` / `intake.manage` |
| PATCH | `/intakes/{id}` | Sửa, mở/đóng | `intake.manage` |
| GET/PUT | `/intakes/{id}/rubrics/{round}` | Xem / tạo phiên bản rubric | `intake.manage` |
| POST | `/intakes/{id}/assign` | Phân công reviewer tự động hoặc thủ công | `application.assign` |

## Hồ sơ ứng viên
| Method | Path | Mô tả | Quyền |
|---|---|---|---|
| POST | `/applications` | Tạo hồ sơ nháp cho đợt | `application.create` |
| GET | `/applications/mine` | Hồ sơ của tôi | `application.read.own` |
| GET/PATCH | `/applications/{id}` | Xem / sửa nháp (khi `DRAFT` hoặc `NEEDS_INFO`) | own hoặc `application.read` |
| POST | `/applications/{id}/documents` | Xin presigned URL tải lên | `application.write.own` |
| POST | `/applications/{id}/documents/{docId}/complete` | Xác nhận đã tải, kích hoạt quét | `application.write.own` |
| GET | `/applications/{id}/documents/{docId}/download` | Presigned URL ngắn hạn, có audit | own hoặc `application.read` |
| POST | `/applications/{id}/submit` | Nộp (kiểm tra đủ trường, consent) | `application.write.own` |
| POST | `/applications/{id}/withdraw` | Rút hồ sơ | `application.write.own` |
| GET | `/applications/{id}/timeline` | Timeline (ứng viên chỉ thấy sự kiện công khai) | own hoặc `application.read` |
| POST | `/applications/{id}/review-requests` | Yêu cầu xem xét lại | `application.write.own` |

## Xét tuyển
| Method | Path | Mô tả | Quyền |
|---|---|---|---|
| GET | `/staff/applications` | Hàng đợi, lọc theo đợt/trạng thái/người phụ trách | `application.read` |
| POST | `/applications/{id}/transitions` | Chuyển trạng thái `{to, reason, version}`; kiểm tra bảng chuyển hợp lệ và quyền theo bước | theo bước |
| PUT | `/applications/{id}/reviews/{round}` | Lưu điểm rubric của tôi | `application.review` |
| POST | `/applications/{id}/reviews/{round}/submit` | Chốt điểm, mở gợi ý AI | `application.review` |
| GET | `/applications/{id}/ai-assessments` | Gợi ý AI (chỉ sau khi chốt điểm) | `application.review` |
| POST | `/applications/{id}/proposals` | Tạo đề xuất quyết định | `decision.propose` |
| GET | `/staff/approvals` | Hàng đợi chờ duyệt | `decision.approve` |
| POST | `/decisions/{id}/approve` | Duyệt `{outcome, reason, applicant_message}` (không được là người đề xuất) | `decision.approve` |
| POST | `/decisions/{id}/return` | Trả lại kèm yêu cầu | `decision.approve` |
| GET/PATCH | `/review-requests` | Xử lý yêu cầu xem xét lại | `application.assign` |

`POST /transitions` trả `409` nếu `version` lỗi thời, `422` nếu chuyển không hợp lệ, `403` nếu thiếu quyền.

## Khoá học (cohort), giai đoạn, nhánh
| Method | Path | Mô tả | Quyền |
|---|---|---|---|
| CRUD | `/programs`, `/programs/{id}/phases`, `/programs/{id}/tracks` | Chương trình, giai đoạn, nhánh | `training.manage` |
| CRUD | `/cohorts` | Khoá học | `cohort.manage` |
| PUT | `/cohorts/{id}/phases/{phaseId}` | Mở/đóng giai đoạn, đặt lịch | `cohort.manage` |
| CRUD | `/cohorts/{id}/classes` | Lớp theo trình độ | `cohort.manage` |
| POST | `/cohorts/{id}/class-suggestions` | Gợi ý xếp lớp theo điểm vòng đánh giá và sức chứa | `cohort.manage` |
| POST | `/cohorts/{id}/class-assignments` | Xác nhận xếp lớp (hàng loạt, chạy nền) | `cohort.manage` |
| POST | `/enrollments/{id}/track` | Gán nhánh (kiểm tra sức chứa) | `cohort.manage` |
| GET | `/enrollments` | Danh sách học viên theo khoá/lớp/nhánh/trạng thái | `cohort.read` |
| POST | `/enrollments/{id}/qualification` | Chốt `qualified`/`not_qualified` kèm lý do (có audit) | `cohort.manage` |
| GET | `/cohorts/{id}/qualification-suggestions` | Đề xuất xét đạt theo quy tắc của mẫu | `cohort.manage` |
| CRUD | `/partners`, `/placements` | Đối tác thực chiến và vị trí | `cohort.manage` |
| GET | `/mentor/learners` | Học viên mentor được giao | `mentor.assess` |
| PUT | `/enrollments/{id}/competency-assessments` | Mentor/giảng viên đánh giá năng lực theo mức | `mentor.assess` |
| GET/PUT | `/enrollments/{id}/stipend` | Xem / ghi nhận phụ cấp theo kỳ (không chi trả) | `cohort.manage` |
| CRUD | `/enrollments/{id}/job-outcomes` | Kết quả việc làm | `cohort.manage` |

## Điểm vòng đánh giá năng lực (nhập từ bên ngoài)
| Method | Path | Mô tả | Quyền |
|---|---|---|---|
| POST | `/intakes/{id}/rounds/{round}/results/import` | Import CSV/JSON điểm; xem trước, báo lỗi theo dòng, rồi xác nhận | `application.assign` |
| GET | `/intakes/{id}/rounds/{round}/results` | Xem điểm đã nhập | `application.read` |

## Đào tạo (khung năng lực, bài đánh giá)
| Method | Path | Mô tả | Quyền |
|---|---|---|---|
| CRUD | `/frameworks`, `/frameworks/{id}/competencies` | Khung năng lực / chuẩn đầu ra (thang mức hoặc phần trăm) | `training.manage` |
| CRUD | `/programs/{id}/courses`, `/assessments` | Môn (tuỳ chọn) và bài đánh giá | `training.manage` |
| PUT | `/assessments/{id}/outcomes` | Map bài ↔ năng lực (kèm trọng số) | `training.manage` |
| POST | `/enrollments/{id}/results` | Nhập điểm thủ công / import CSV | `training.manage` |
| POST | `/integrations/lms/sync` | Chạy đồng bộ ngay | `integration.manage` |
| GET | `/training/attainment` | Attainment tổng hợp, lọc theo chương trình/khoá/chuẩn | `training.read` |
| GET | `/training/outcomes/{id}/breakdown` | Đóng góp theo môn/bài, phân bố điểm | `training.read` |
| GET | `/training/coverage-gaps` | Chuẩn đầu ra chưa có bài đo | `training.read` |

## Chất lượng và báo cáo
| Method | Path | Mô tả | Quyền |
|---|---|---|---|
| GET | `/quality/alerts` | Danh sách cảnh báo | `training.read` |
| PATCH | `/quality/alerts/{id}` | Nhận xử lý, đóng, bỏ qua | `training.manage` |
| POST | `/quality/runs` | Chạy kiểm tra ngay | `training.manage` |
| POST | `/reports/improvement` | Yêu cầu soạn báo cáo (chạy nền, trả `202`) | `training.manage` |
| GET/PATCH | `/reports/improvement/{id}` | Xem, sửa bản nháp | `training.read` / `training.manage` |
| POST | `/reports/improvement/{id}/approve` | Duyệt | `training.manage` |
| CRUD | `/reports/improvement/{id}/actions` | Hành động cải tiến | `training.manage` |

## Dashboard và export
| Method | Path | Mô tả | Quyền |
|---|---|---|---|
| GET | `/analytics/admissions/funnel` | Funnel theo đợt | `analytics.read` |
| GET | `/analytics/admissions/processing-time` | Thời gian xử lý | `analytics.read` |
| GET | `/analytics/admissions/reviewer-load` | Tải reviewer | `analytics.read` |
| GET | `/exports/{dataset}.csv` | Export dataset đã khử định danh | `export.read` |

## Trợ lý AI
| Method | Path | Mô tả | Quyền |
|---|---|---|---|
| POST | `/assistant/chat` | `{session_id?, message}` → stream SSE: `token`, `citations`, `done` | `assistant.use` |
| POST | `/assistant/messages/{id}/feedback` | 👍/👎 | `assistant.use` |
| GET/POST | `/kb/documents` | Danh sách / upload tài liệu | `kb.manage` |
| DELETE | `/kb/documents/{id}` | Gỡ tài liệu | `kb.manage` |
| POST | `/kb/eval/run` | Chạy bộ câu hỏi kiểm thử, trả báo cáo | `kb.manage` |

## Nền tảng (chỉ `platform_admin`)
| Method | Path | Mô tả |
|---|---|---|
| GET/POST | `/platform/organizations` | Danh sách / tạo tổ chức |
| PATCH | `/platform/organizations/{id}` | Cấu hình, giới hạn gói, khoá tổ chức |
| POST | `/platform/organizations/{id}/templates` | Nạp mẫu chương trình (kiểm tra JSON Schema, xem trước thay đổi) |
| POST | `/platform/organizations/{id}/export` | Xuất toàn bộ dữ liệu (xác nhận hai bước, có audit) |

Mọi truy cập chéo tổ chức qua nhóm này bắt buộc có `reason` và được ghi audit.

## Hệ thống
| Method | Path | Mô tả | Quyền |
|---|---|---|---|
| GET | `/audit-logs` | Tra cứu nhật ký | `audit.read` |
| POST | `/webhooks/{provider}` | Nhận webhook CRM/LMS (xác thực chữ ký) | chữ ký |
| GET | `/healthz`, `/readyz` | Sức khoẻ | public |

## Bảng permission theo vai trò

| Permission | applicant | reviewer | approver | training_manager | admin |
|---|:-:|:-:|:-:|:-:|:-:|
| `application.create`, `application.read.own`, `application.write.own` | ✓ | | | | |
| `application.read` | | ✓ | ✓ | | ✓ |
| `application.review` | | ✓ | | | |
| `application.assign` | | | | | ✓ |
| `decision.propose` | | ✓ | | | |
| `decision.approve` | | | ✓ | | |
| `intake.read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `intake.manage` | | | | | ✓ |
| `user.manage`, `integration.manage`, `kb.manage`, `audit.read` | | | | | ✓ |
| `analytics.read` | | ✓ | ✓ | ✓ | ✓ |
| `export.read` | | | | ✓ | ✓ |
| `training.read` | | | | ✓ | ✓ |
| `training.manage` | | | | ✓ | |
| `assistant.use` | ✓ | ✓ | ✓ | ✓ | ✓ |

Permission bổ sung cho vận hành khoá học:

| Permission | cohort_manager | mentor | training_manager | admin | platform_admin |
|---|:-:|:-:|:-:|:-:|:-:|
| `cohort.read` | ✓ | | ✓ | ✓ | |
| `cohort.manage` | ✓ | | | | |
| `mentor.assess` | | ✓ | ✓ | | |
| `platform.manage` | | | | | ✓ |

Mentor chỉ thấy học viên được giao trong `placements`; ràng buộc này được kiểm tra ở tầng truy vấn, không chỉ ở giao diện.

Một người có thể giữ nhiều vai trò, nhưng ràng buộc nghiệp vụ vẫn áp dụng: người đề xuất không được duyệt chính đề xuất đó.
