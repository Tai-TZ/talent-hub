/** Nhãn và sắc thái hiển thị cho các giá trị trạng thái do BE trả về (khu nhân sự/quản trị dùng tiếng Việt). */

export type Tone = "info" | "success" | "warning" | "danger";
type Entry = readonly [label: string, tone: Tone];

function lookup(table: Record<string, Entry>, key: string | null | undefined): Entry {
  if (!key) return ["—", "info"];
  return table[key] ?? [key, "info"];
}

const APPLICATION_STATUS: Record<string, Entry> = {
  DRAFT: ["Bản nháp", "info"],
  SUBMITTED: ["Đã nộp", "info"],
  IN_ROUND: ["Đang xét", "info"],
  NEEDS_INFO: ["Cần bổ sung", "warning"],
  PENDING_APPROVAL: ["Chờ phê duyệt", "warning"],
  ACCEPTED: ["Được nhận", "success"],
  REJECTED: ["Không đạt", "danger"],
  WAITLISTED: ["Dự bị", "warning"],
  ENROLLED: ["Đã nhập học", "success"],
  WITHDRAWN: ["Đã rút hồ sơ", "danger"],
};

const INTAKE_STATUS: Record<string, Entry> = {
  draft: ["Nháp", "info"],
  open: ["Đang mở", "success"],
  closed: ["Đã đóng", "warning"],
  archived: ["Lưu trữ", "info"],
};

const TIER: Record<string, Entry> = {
  invite: ["Nên mời", "success"],
  review: ["Cần xem xét", "warning"],
  decline_likely: ["Khả năng loại", "danger"],
};

const OUTCOME: Record<string, Entry> = {
  accepted: ["Nhận", "success"],
  rejected: ["Không nhận", "danger"],
  waitlisted: ["Dự bị", "warning"],
};

const ENROLLMENT_STATUS: Record<string, Entry> = {
  active: ["Đang học", "info"],
  withdrawn: ["Đã rút", "danger"],
  qualified: ["Đạt", "success"],
  not_qualified: ["Chưa đạt", "danger"],
};

const ACCOUNT_STATUS: Record<string, Entry> = {
  invited: ["Đã mời", "warning"],
  active: ["Hoạt động", "success"],
  suspended: ["Bị khoá", "danger"],
};

const JOB_STATUS: Record<string, Entry> = {
  queued: ["Đang chờ", "info"],
  running: ["Đang chạy", "info"],
  done: ["Hoàn tất", "success"],
  failed: ["Lỗi", "danger"],
};

const DOC_STATUS: Record<string, Entry> = {
  ready: ["Sẵn sàng", "success"],
  failed: ["Lỗi xử lý", "danger"],
  retired: ["Đã gỡ", "warning"],
};

const SUGGESTION: Record<string, Entry> = {
  qualified: ["Gợi ý: đạt", "success"],
  not_qualified: ["Gợi ý: chưa đạt", "danger"],
  pending: ["Chưa đủ đánh giá", "warning"],
  no_targets: ["Chưa có chuẩn năng lực", "info"],
};

const RECOMMENDATION: Record<string, Entry> = {
  advance: ["Cho đi tiếp", "success"],
  waitlist: ["Dự bị", "warning"],
  reject: ["Không đạt", "danger"],
};

export const RECOMMENDATIONS = ["advance", "waitlist", "reject"] as const;

export const applicationStatus = (s: string | null | undefined) => lookup(APPLICATION_STATUS, s);
export const intakeStatus = (s: string | null | undefined) => lookup(INTAKE_STATUS, s);
export const tierLabel = (s: string | null | undefined) => lookup(TIER, s);
export const outcomeLabel = (s: string | null | undefined) => lookup(OUTCOME, s);
export const enrollmentStatus = (s: string | null | undefined) => lookup(ENROLLMENT_STATUS, s);
export const accountStatus = (s: string | null | undefined) => lookup(ACCOUNT_STATUS, s);
export const jobStatus = (s: string | null | undefined) => lookup(JOB_STATUS, s);
export const docStatus = (s: string | null | undefined) => lookup(DOC_STATUS, s);
export const suggestionLabel = (s: string | null | undefined) => lookup(SUGGESTION, s);
export const recommendationLabel = (s: string | null | undefined) => lookup(RECOMMENDATION, s);

export const ROLE_LABELS: Record<string, string> = {
  applicant: "Ứng viên",
  reviewer: "Người chấm hồ sơ",
  approver: "Người phê duyệt",
  cohort_manager: "Quản lý khoá học",
  training_manager: "Quản lý đào tạo",
  mentor: "Mentor",
  admin: "Quản trị viên (IT)",
  platform_admin: "Quản trị nền tảng",
};

export const COST_CATEGORY_LABELS: Record<string, string> = {
  stipend: "Phụ cấp học viên",
  ai: "Chi phí AI",
  infrastructure: "Hạ tầng",
  partner: "Đối tác",
  operations: "Vận hành",
  other: "Khác",
};

export const SETTING_LABELS: Record<string, string> = {
  usd_vnd_rate: "Tỷ giá USD/VND",
  ai_monthly_budget_usd: "Trần chi phí AI hằng tháng (USD)",
  ai_engine: "Động cơ sàng lọc AI",
  stipend_vnd_per_month: "Phụ cấp mỗi học viên mỗi tháng (VND)",
  invite_ttl_hours: "Thời hạn link lời mời (giờ)",
};

export const FIELD_LABELS: Record<string, string> = {
  "profile.full_name": "Họ tên",
  "profile.phone": "Số điện thoại",
  "content.education": "Học vấn",
  "content.skills": "Kỹ năng",
  "content.essays.motivation": "Động lực",
};

const EVENT_LABELS: Record<string, string> = {
  "application.created": "Tạo hồ sơ",
  "application.submitted": "Đã nộp hồ sơ",
  "status.in_round": "Bắt đầu xét vòng đầu",
  "round.advanced": "Chuyển sang vòng tiếp theo",
  "info.requested": "Cần bổ sung thông tin",
  "application.info_provided": "Đã bổ sung thông tin",
  "decision.proposed": "Có đề xuất quyết định, chờ phê duyệt",
  "decision.returned": "Đề xuất được trả lại để xem xét thêm",
  "decision.accepted": "Hồ sơ được nhận",
  "decision.rejected": "Hồ sơ không đạt",
  "decision.waitlisted": "Vào danh sách dự bị",
  "application.enrolled": "Đã nhập học",
  "application.withdrawn": "Đã rút hồ sơ",
  "round.started": "Bắt đầu xét vòng đầu",
};

export function eventLabel(type: string): string {
  return EVENT_LABELS[type] ?? (type.startsWith("status.") ? "Cập nhật trạng thái" : type);
}
