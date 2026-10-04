# Mô hình dữ liệu chi tiết

Quy ước: khoá chính `id uuid` (UUIDv7), mọi bảng có `created_at`, `updated_at timestamptz`. **Mọi bảng thuộc về một tổ chức đều có `organization_id uuid NOT NULL` và policy RLS** (xem [09-multi-tenancy.md](09-multi-tenancy.md)); các bảng bên dưới mặc định có cột này trừ khi ghi chú "toàn cục", và mọi ràng buộc `UNIQUE` đều gồm `organization_id`. Enum lưu bằng `text` + `CHECK` (dễ migrate hơn enum của Postgres). Xoá mềm bằng `deleted_at` cho bảng chứa PII. Cột đánh dấu 🔒 mã hoá ở tầng ứng dụng.

## 0. Tổ chức

| Bảng | Cột chính | Ghi chú |
|---|---|---|
| `organizations` (toàn cục) | `slug`, `name`, `default_locale`, `timezone`, `branding` (jsonb), `status`, `plan_limits` (jsonb) | `UNIQUE(slug)` |
| `org_settings` | `key`, `value` (jsonb) | `UNIQUE(organization_id, key)` |
| `org_idp_connections` | `type`, `issuer`, `client_id`, `client_secret` 🔒, `allowed_tenant_ids`, `staff_email_domains` | |
| `org_llm_settings` | `task`, `provider`, `model`, `api_key` 🔒 (tuỳ chọn) | |
| `program_templates` | `code`, `version`, `definition` (jsonb), `applied_at` | Mẫu chương trình, xem mục 6 của tài liệu đa tổ chức |

## 1. Danh tính

| Bảng | Cột chính | Ràng buộc / index |
|---|---|---|
| `users` (toàn cục) | `email` (citext), `email_verified_at`, `full_name`, `password_hash` (null nếu chỉ dùng Microsoft), `must_change_password`, `is_active`, `failed_logins`, `locked_until`, `last_login_at` | `UNIQUE(email)` |
| `org_memberships` | `user_id`, `status` (invited/active/suspended) | `UNIQUE(organization_id, user_id)` |
| `roles` (toàn cục) | `code` (applicant, reviewer, approver, cohort_manager, training_manager, mentor, admin, platform_admin) | `UNIQUE(code)` |
| `user_roles` | `membership_id`, `role_id`, `granted_by`, `granted_at` | PK `(membership_id, role_id)` |
| `oauth_accounts` (toàn cục) | `user_id`, `provider` (`microsoft`), `issuer`, `subject`, `tenant_id`, `linked_at` | `UNIQUE(issuer, subject)` |
| `invitations` | `membership_id`, `token_hash`, `expires_at`, `used_at`, `created_by` | index `token_hash` |
| `refresh_tokens` | `user_id`, `organization_id`, `token_hash`, `family_id`, `expires_at`, `revoked_at`, `replaced_by` | index `(family_id)` |
| `applicant_profiles` | `membership_id`, `phone` 🔒, `national_id` 🔒, `date_of_birth` 🔒, `address` 🔒, `education` (jsonb), `experience` (jsonb), `links` (jsonb) | `UNIQUE(membership_id)` |
| `consents` | `membership_id`, `purpose`, `policy_version`, `granted_at`, `revoked_at`, `ip` | index `(membership_id, purpose)` |

## 2. Tuyển sinh

| Bảng | Cột chính | Ràng buộc / index |
|---|---|---|
| `intakes` | `program_id`, `cohort_id` (khoá sẽ nhập học), `name`, `opens_at`, `closes_at`, `quota`, `status` (draft/open/closed/archived), `ai_screening_enabled`, `rounds` (jsonb: dãy vòng, loại `review`/`assessment`/`interview`), `approval_mode` (two_level/single_level), `eligibility_rules` (jsonb), `form_schema` (jsonb) | `CHECK(closes_at > opens_at)` |
| `rubrics` | `intake_id`, `round` (screening/test/interview), `criteria` (jsonb: id, tên, mô tả, trọng số, thang điểm), `version` | `UNIQUE(intake_id, round, version)` |
| `applications` | `intake_id`, `applicant_id` (→ `org_memberships`), `status`, `current_round`, `version int` (khoá lạc quan), `form_data` (jsonb), `submitted_at`, `assigned_reviewer_id`, `crm_external_id`, `withdrawn_at` | `UNIQUE(intake_id, applicant_id)`; index `(intake_id, status, current_round)`, `(assigned_reviewer_id, status)` |
| `application_documents` | `application_id`, `kind`, `filename`, `content_type`, `size`, `storage_key`, `sha256`, `scan_status` (pending/clean/infected/error) | index `application_id` |
| `application_events` | `application_id`, `actor_id`, `type`, `from_status`, `to_status`, `payload` (jsonb), `visible_to_applicant bool` | index `(application_id, created_at)`. Chỉ thêm, không sửa/xoá |
| `reviews` | `application_id`, `reviewer_id`, `round`, `rubric_id`, `scores` (jsonb), `total_score`, `comment`, `recommendation` (advance/reject/waitlist/accept/need_info), `submitted_at` | `UNIQUE(application_id, reviewer_id, round)` |
| `ai_assessments` | `application_id`, `round`, `provider`, `model`, `prompt_version`, `scores` (jsonb), `rationale`, `input_fields` (mảng tên trường đã dùng), `created_at` | index `application_id` |
| `decisions` | `application_id`, `outcome` (accepted/rejected/waitlisted), `proposed_by`, `proposed_at`, `proposal_reason`, `decided_by`, `decided_at`, `decision_reason`, `applicant_message`, `status` (pending/approved/returned) | `CHECK(decided_by IS NULL OR decided_by <> proposed_by)` |
| `review_requests` | `application_id`, `reason`, `status`, `handled_by`, `resolution` | Ứng viên yêu cầu xem xét lại |
| `round_results` | `application_id`, `round`, `source` (review/import/provider), `score`, `max_score`, `details` (jsonb), `imported_by`, `imported_at` | Điểm vòng đánh giá năng lực nhập từ CSV/API; `UNIQUE(application_id, round)` |

## 3. Chương trình, khoá học, năng lực

Mô hình: **Program → Cohort → Phase → Track**. Chương trình theo môn/tín chỉ dùng thêm `courses` và `assessments` (tuỳ chọn, theo mẫu).

| Bảng | Cột chính | Ràng buộc / index |
|---|---|---|
| `programs` | `code`, `name` (jsonb vi/en), `kind` (cohort/semester), `framework_id`, `template_id` | `UNIQUE(organization_id, code)` |
| `phases` | `program_id`, `key`, `name` (jsonb), `ordinal`, `weeks` | `UNIQUE(program_id, key)` |
| `tracks` | `program_id`, `key`, `name` (jsonb), `framework_targets` (jsonb: năng lực → mức mục tiêu) | `UNIQUE(program_id, key)` |
| `cohorts` | `program_id`, `code`, `name`, `starts_on`, `capacity`, `status` (planned/running/completed) | `UNIQUE(program_id, code)` |
| `cohort_phases` | `cohort_id`, `phase_id`, `starts_on`, `ends_on`, `status` (not_started/open/closed) | PK `(cohort_id, phase_id)` |
| `cohort_classes` | `cohort_id`, `name`, `level`, `capacity` | Lớp xếp theo trình độ |
| `enrollments` | `application_id`, `membership_id`, `cohort_id`, `class_id`, `track_id` (null đến khi gán nhánh), `status` (active/withdrawn/qualified/not_qualified), `qualification_decided_by`, `lms_external_id`, `enrolled_at` | `UNIQUE(application_id)`; index `(cohort_id, status)` |
| `partner_organizations` | `name`, `contact`, `status` | Doanh nghiệp đối tác |
| `placements` | `enrollment_id`, `partner_id`, `mentor_membership_id`, `project`, `starts_on`, `ends_on`, `status` | index `(partner_id)`, `(mentor_membership_id)` |
| `stipend_entries` | `enrollment_id`, `period` (YYYY-MM), `amount`, `currency`, `eligibility` (eligible/ineligible/pending), `paid_marked_by`, `paid_marked_at` | Chỉ ghi nhận; `UNIQUE(enrollment_id, period)` |
| `job_outcomes` | `enrollment_id`, `employer`, `offer_status` (offered/accepted/declined/none), `offered_at`, `follow_up` (jsonb: mốc 30/90/180 ngày) | |

### Khung năng lực và chuẩn đầu ra

| Bảng | Cột chính | Ràng buộc / index |
|---|---|---|
| `frameworks` | `code` (sfia9, plo-cs…), `name`, `scale_type` (`level`/`percent`), `max_level` (cho thang mức, SFIA = 7), `default_threshold` | `UNIQUE(organization_id, code)` |
| `competencies` | `framework_id`, `code` (ví dụ kỹ năng SFIA hoặc PLO1), `name` (jsonb), `description`, `threshold` (null = dùng mặc định của khung) | `UNIQUE(framework_id, code)` |
| `competency_assessments` | `enrollment_id`, `competency_id`, `phase_id`, `level` hoặc `score`, `assessor_membership_id`, `evidence`, `comment`, `assessed_at` | Đánh giá theo mức của mentor/giảng viên; index `(enrollment_id, competency_id, assessed_at)` |
| `courses` (tuỳ chọn) | `program_id`, `code`, `name`, `credits`, `lms_external_id` | Cho chương trình theo môn |
| `assessments` | `program_id`, `course_id` (null được), `phase_id` (null được), `name`, `type`, `max_score`, `is_required`, `due_at`, `lms_external_id` | |
| `assessment_outcome_map` | `assessment_id`, `competency_id`, `weight` (0–1] | PK `(assessment_id, competency_id)` |
| `assessment_results` | `enrollment_id`, `assessment_id`, `score`, `max_score`, `source` (lms/manual/import), `synced_at`, `raw` (jsonb) | `UNIQUE(enrollment_id, assessment_id)`; index `assessment_id` |
| `competency_attainment` | `enrollment_id`, `competency_id`, `value`, `target`, `met bool`, `coverage`, `computed_at` | `UNIQUE(enrollment_id, competency_id)` |

Công thức:
- **Thang phần trăm:** `value = Σ(score_i / max_i × w_i) / Σ(w_i)` trên các bài đã có điểm; `coverage = Σ(w đã có điểm) / Σ(w tất cả)`; `met = value ≥ threshold`.
- **Thang mức:** `value` = mức mới nhất trong `competency_assessments` (trong phạm vi các phase đã đóng); `target` lấy từ `tracks.framework_targets` của nhánh học viên; `met = value ≥ target`; `coverage` = tỉ lệ năng lực mục tiêu của nhánh đã có đánh giá.
- Khi `coverage` thấp thì kết quả được gắn nhãn "chưa đủ dữ liệu", không đếm vào tỉ lệ đạt.
- `enrollments.status = qualified` không tự động theo công thức: hệ thống chỉ **đề xuất** theo quy tắc `qualification` của mẫu, cohort_manager chốt và có audit.

## 4. Chất lượng và báo cáo

| Bảng | Cột chính |
|---|---|
| `data_quality_alerts` | `rule_code`, `severity` (low/medium/high), `subject_type`, `subject_id`, `details` (jsonb), `status` (open/acknowledged/resolved/dismissed), `assignee_id`, `fingerprint` (chống trùng, `UNIQUE` với alert đang mở) |
| `improvement_reports` | `program_id`, `cohort_id` (null được), `period`, `status` (draft/approved), `content_md`, `metrics_snapshot` (jsonb), `model`, `approved_by` |
| `improvement_actions` | `report_id`, `title`, `owner_id`, `due_at`, `status`, `outcome_note` |

## 5. Trợ lý AI

| Bảng | Cột chính |
|---|---|
| `kb_documents` | `title`, `source_type` (file/url), `storage_key`, `visibility` (public/internal), `version`, `status` (processing/ready/failed/retired), `checksum` |
| `kb_chunks` | `organization_id`, `document_id`, `ordinal`, `heading_path`, `content`, `tsv` (tsvector), `embedding` (vector), `embedding_model`, `token_count`. Index GIN `tsv`, HNSW `embedding` |
| `chat_sessions` | `membership_id`, `scope` (applicant/staff) |
| `chat_messages` | `session_id`, `role`, `content`, `citations` (jsonb: chunk_id, document, heading), `refused bool`, `feedback` (up/down/null), `latency_ms`, `model` |
| `rag_eval_cases` | `question`, `expected_document_ids`, `expected_answer_notes`, `scope` |

## 6. Hệ thống

| Bảng | Cột chính |
|---|---|
| `audit_logs` | `actor_id`, `action`, `entity_type`, `entity_id`, `before` (jsonb), `after` (jsonb), `ip`, `request_id`, `at`. Chỉ thêm; quyền DB của app không có UPDATE/DELETE |
| `outbox` | `topic`, `payload`, `status` (pending/sent/failed), `attempts`, `next_attempt_at`, `idempotency_key UNIQUE` |
| `integration_connections` | `kind` (crm/lms), `provider`, `config` (jsonb, secret mã hoá), `enabled` |
| `sync_runs` | `connection_id`, `started_at`, `finished_at`, `status`, `stats` (jsonb), `error` |
| `webhook_events` | `provider`, `external_id`, `signature_ok`, `payload`, `processed_at`, `UNIQUE(provider, external_id)` |

## 7. Schema `analytics` (cho Power BI)

Chỉ gồm view đã khử định danh, người dùng DB `powerbi_reader` chỉ có `SELECT` trên schema này; mỗi view có cột `organization_id` và Power BI dùng vai trò DB riêng cho từng tổ chức (RLS vẫn áp dụng), không có vai trò xem chéo tổ chức.

| View | Nội dung |
|---|---|
| `analytics.admission_funnel` | Số hồ sơ theo đợt, vòng, trạng thái, tuần |
| `analytics.processing_time` | Thời gian trung vị/P90 mỗi chặng |
| `analytics.reviewer_load` | Số hồ sơ và thời gian chấm theo reviewer (mã hoá danh tính) |
| `analytics.outcome_attainment_summary` | Tỉ lệ đạt theo chương trình, khoá, nhánh, năng lực/chuẩn đầu ra |
| `analytics.data_quality_summary` | Số cảnh báo theo loại, mức, thời gian xử lý |
| `analytics.assistant_usage` | Số câu hỏi, tỉ lệ từ chối, tỉ lệ feedback tốt |
| `analytics.cohort_outcomes` | Số học viên đạt, đề nghị việc làm, phụ cấp theo khoá và nhánh |

Mã ứng viên trong view là `sha256(id || salt)`; không có tên, email, số điện thoại.

## 8. Retention

Mặc định (chờ pháp chế xác nhận): hồ sơ không trúng tuyển xoá hoặc ẩn danh sau 24 tháng; tài liệu tải lên xoá sau 12 tháng từ khi kết thúc đợt; `audit_logs` giữ 5 năm; `chat_messages` giữ 12 tháng.
