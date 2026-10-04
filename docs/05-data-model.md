# Mô hình dữ liệu chi tiết

Quy ước: khoá chính `id uuid` (UUIDv7), mọi bảng có `created_at`, `updated_at timestamptz`. Enum lưu bằng `text` + `CHECK` (dễ migrate hơn enum của Postgres). Xoá mềm bằng `deleted_at` cho bảng chứa PII. Cột đánh dấu 🔒 mã hoá ở tầng ứng dụng.

## 1. Danh tính

| Bảng | Cột chính | Ràng buộc / index |
|---|---|---|
| `users` | `email` (citext), `email_verified_at`, `full_name`, `password_hash` (null nếu chỉ dùng Microsoft), `must_change_password`, `is_active`, `failed_logins`, `locked_until`, `last_login_at` | `UNIQUE(email)` |
| `roles` | `code` (applicant, reviewer, approver, training_manager, admin) | `UNIQUE(code)` |
| `user_roles` | `user_id`, `role_id`, `granted_by`, `granted_at` | PK `(user_id, role_id)` |
| `oauth_accounts` | `user_id`, `provider` (`microsoft`), `issuer`, `subject`, `tenant_id`, `linked_at` | `UNIQUE(issuer, subject)` |
| `invitations` | `user_id`, `token_hash`, `expires_at`, `used_at`, `created_by` | index `token_hash` |
| `refresh_tokens` | `user_id`, `token_hash`, `family_id`, `expires_at`, `revoked_at`, `replaced_by` | index `(family_id)` |
| `applicant_profiles` | `user_id`, `phone` 🔒, `national_id` 🔒, `date_of_birth` 🔒, `address` 🔒, `education` (jsonb), `experience` (jsonb), `links` (jsonb) | `UNIQUE(user_id)` |
| `consents` | `user_id`, `purpose`, `policy_version`, `granted_at`, `revoked_at`, `ip` | index `(user_id, purpose)` |

## 2. Tuyển sinh

| Bảng | Cột chính | Ràng buộc / index |
|---|---|---|
| `programs` | `code`, `name`, `description`, `outcome_threshold` (mặc định 0.70) | `UNIQUE(code)` |
| `intakes` | `program_id`, `name`, `opens_at`, `closes_at`, `quota`, `status` (draft/open/closed/archived), `ai_screening_enabled`, `rounds` (jsonb: thứ tự và loại vòng), `form_schema` (jsonb) | `CHECK(closes_at > opens_at)` |
| `rubrics` | `intake_id`, `round` (screening/test/interview), `criteria` (jsonb: id, tên, mô tả, trọng số, thang điểm), `version` | `UNIQUE(intake_id, round, version)` |
| `applications` | `intake_id`, `applicant_id`, `status`, `version int` (khoá lạc quan), `form_data` (jsonb), `submitted_at`, `assigned_reviewer_id`, `crm_external_id`, `withdrawn_at` | `UNIQUE(intake_id, applicant_id)`; index `(intake_id, status)`, `(assigned_reviewer_id, status)` |
| `application_documents` | `application_id`, `kind`, `filename`, `content_type`, `size`, `storage_key`, `sha256`, `scan_status` (pending/clean/infected/error) | index `application_id` |
| `application_events` | `application_id`, `actor_id`, `type`, `from_status`, `to_status`, `payload` (jsonb), `visible_to_applicant bool` | index `(application_id, created_at)`. Chỉ thêm, không sửa/xoá |
| `reviews` | `application_id`, `reviewer_id`, `round`, `rubric_id`, `scores` (jsonb), `total_score`, `comment`, `recommendation` (advance/reject/waitlist/accept/need_info), `submitted_at` | `UNIQUE(application_id, reviewer_id, round)` |
| `ai_assessments` | `application_id`, `round`, `provider`, `model`, `prompt_version`, `scores` (jsonb), `rationale`, `input_fields` (mảng tên trường đã dùng), `created_at` | index `application_id` |
| `decisions` | `application_id`, `outcome` (accepted/rejected/waitlisted), `proposed_by`, `proposed_at`, `proposal_reason`, `decided_by`, `decided_at`, `decision_reason`, `applicant_message`, `status` (pending/approved/returned) | `CHECK(decided_by IS NULL OR decided_by <> proposed_by)` |
| `review_requests` | `application_id`, `reason`, `status`, `handled_by`, `resolution` | Ứng viên yêu cầu xem xét lại |
| `enrollments` | `application_id`, `program_id`, `cohort`, `status`, `lms_external_id`, `enrolled_at` | `UNIQUE(application_id)` |

## 3. Đào tạo và chuẩn đầu ra

| Bảng | Cột chính | Ràng buộc / index |
|---|---|---|
| `courses` | `program_id`, `code`, `name`, `credits`, `lms_external_id` | `UNIQUE(program_id, code)` |
| `learning_outcomes` | `program_id`, `code` (PLO1…), `description`, `threshold` (null = dùng của program) | `UNIQUE(program_id, code)` |
| `assessments` | `course_id`, `name`, `type` (quiz/assignment/project/exam), `max_score`, `is_required`, `due_at`, `lms_external_id` | index `course_id` |
| `assessment_outcome_map` | `assessment_id`, `outcome_id`, `weight` (0–1] | PK `(assessment_id, outcome_id)` |
| `assessment_results` | `enrollment_id`, `assessment_id`, `score`, `max_score`, `source` (lms/manual), `synced_at`, `raw` (jsonb) | `UNIQUE(enrollment_id, assessment_id)`; index `assessment_id` |
| `outcome_attainment` | `enrollment_id`, `outcome_id`, `value` (0–1), `met bool`, `coverage` (tỉ lệ bài đã có điểm), `computed_at` | `UNIQUE(enrollment_id, outcome_id)` |

Công thức: `value = Σ(score_i / max_i × w_i) / Σ(w_i)` trên các bài đã có điểm; `coverage = Σ(w đã có điểm) / Σ(w tất cả)`. `met = value ≥ threshold`. Khi `coverage` thấp thì kết quả được gắn nhãn "chưa đủ dữ liệu", không đếm vào tỉ lệ đạt.

## 4. Chất lượng và báo cáo

| Bảng | Cột chính |
|---|---|
| `data_quality_alerts` | `rule_code`, `severity` (low/medium/high), `subject_type`, `subject_id`, `details` (jsonb), `status` (open/acknowledged/resolved/dismissed), `assignee_id`, `fingerprint` (chống trùng, `UNIQUE` với alert đang mở) |
| `improvement_reports` | `program_id`, `period`, `status` (draft/approved), `content_md`, `metrics_snapshot` (jsonb), `model`, `approved_by` |
| `improvement_actions` | `report_id`, `title`, `owner_id`, `due_at`, `status`, `outcome_note` |

## 5. Trợ lý AI

| Bảng | Cột chính |
|---|---|
| `kb_documents` | `title`, `source_type` (file/url), `storage_key`, `visibility` (public/internal), `version`, `status` (processing/ready/failed/retired), `checksum` |
| `kb_chunks` | `document_id`, `ordinal`, `heading_path`, `content`, `tsv` (tsvector), `embedding` (vector), `embedding_model`, `token_count`. Index GIN `tsv`, HNSW `embedding` |
| `chat_sessions` | `user_id`, `scope` (applicant/staff) |
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

Chỉ gồm view đã khử định danh, người dùng DB `powerbi_reader` chỉ có `SELECT` trên schema này.

| View | Nội dung |
|---|---|
| `analytics.admission_funnel` | Số hồ sơ theo đợt, vòng, trạng thái, tuần |
| `analytics.processing_time` | Thời gian trung vị/P90 mỗi chặng |
| `analytics.reviewer_load` | Số hồ sơ và thời gian chấm theo reviewer (mã hoá danh tính) |
| `analytics.outcome_attainment_summary` | Tỉ lệ đạt theo chương trình, khoá, chuẩn đầu ra, môn |
| `analytics.data_quality_summary` | Số cảnh báo theo loại, mức, thời gian xử lý |
| `analytics.assistant_usage` | Số câu hỏi, tỉ lệ từ chối, tỉ lệ feedback tốt |

Mã ứng viên trong view là `sha256(id || salt)`; không có tên, email, số điện thoại.

## 8. Retention

Mặc định (chờ pháp chế xác nhận): hồ sơ không trúng tuyển xoá hoặc ẩn danh sau 24 tháng; tài liệu tải lên xoá sau 12 tháng từ khi kết thúc đợt; `audit_logs` giữ 5 năm; `chat_messages` giữ 12 tháng.
