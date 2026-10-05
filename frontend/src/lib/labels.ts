/** Nhãn và sắc thái hiển thị cho các giá trị trạng thái do BE trả về, theo ngôn ngữ giao diện.
 *
 * Trong component dùng `useLabels()` (components/providers). Các export ở cuối là bản tiếng Việt cho mã cũ.
 */
import type { Locale } from "./i18n";

export type Tone = "info" | "success" | "warning" | "danger";
type Entry = readonly [label: string, tone: Tone];
type Bi = readonly [vi: string, en: string];
type Table = Record<string, readonly [vi: string, en: string, tone: Tone]>;

const APPLICATION_STATUS: Table = {
  DRAFT: ["Bản nháp", "Draft", "info"],
  SUBMITTED: ["Đã nộp", "Submitted", "info"],
  IN_ROUND: ["Đang xét", "In review", "info"],
  NEEDS_INFO: ["Cần bổ sung", "Needs information", "warning"],
  PENDING_APPROVAL: ["Chờ phê duyệt", "Pending approval", "warning"],
  ACCEPTED: ["Được nhận", "Accepted", "success"],
  REJECTED: ["Không đạt", "Not accepted", "danger"],
  WAITLISTED: ["Dự bị", "Waitlisted", "warning"],
  ENROLLED: ["Đã nhập học", "Enrolled", "success"],
  WITHDRAWN: ["Đã rút hồ sơ", "Withdrawn", "danger"],
};

const INTAKE_STATUS: Table = {
  draft: ["Nháp", "Draft", "info"],
  open: ["Đang mở", "Open", "success"],
  closed: ["Đã đóng", "Closed", "warning"],
  archived: ["Lưu trữ", "Archived", "info"],
};

const TIER: Table = {
  invite: ["Nên mời", "Invite", "success"],
  review: ["Cần xem xét", "Review", "warning"],
  decline_likely: ["Khả năng loại", "Likely decline", "danger"],
};

const OUTCOME: Table = {
  accepted: ["Nhận", "Accept", "success"],
  rejected: ["Không nhận", "Reject", "danger"],
  waitlisted: ["Dự bị", "Waitlist", "warning"],
};

const ENROLLMENT_STATUS: Table = {
  active: ["Đang học", "Studying", "info"],
  withdrawn: ["Đã rút", "Withdrawn", "danger"],
  qualified: ["Đạt", "Qualified", "success"],
  not_qualified: ["Chưa đạt", "Not qualified", "danger"],
};

const ACCOUNT_STATUS: Table = {
  invited: ["Đã mời", "Invited", "warning"],
  active: ["Hoạt động", "Active", "success"],
  suspended: ["Bị khoá", "Suspended", "danger"],
};

const JOB_STATUS: Table = {
  queued: ["Đang chờ", "Queued", "info"],
  running: ["Đang chạy", "Running", "info"],
  done: ["Hoàn tất", "Done", "success"],
  failed: ["Lỗi", "Failed", "danger"],
};

const DOC_STATUS: Table = {
  ready: ["Sẵn sàng", "Ready", "success"],
  failed: ["Lỗi xử lý", "Processing failed", "danger"],
  retired: ["Đã gỡ", "Retired", "warning"],
};

const SUGGESTION: Table = {
  qualified: ["Gợi ý: đạt", "Suggested: qualified", "success"],
  not_qualified: ["Gợi ý: chưa đạt", "Suggested: not qualified", "danger"],
  pending: ["Chưa đủ đánh giá", "Not enough assessments", "warning"],
  no_targets: ["Chưa có chuẩn năng lực", "No competency targets", "info"],
};

const RECOMMENDATION: Table = {
  advance: ["Cho đi tiếp", "Advance", "success"],
  waitlist: ["Dự bị", "Waitlist", "warning"],
  reject: ["Không đạt", "Reject", "danger"],
};

export const RECOMMENDATIONS = ["advance", "waitlist", "reject"] as const;

const ROLES: Record<string, Bi> = {
  applicant: ["Ứng viên", "Applicant"],
  reviewer: ["Người chấm hồ sơ", "Reviewer"],
  approver: ["Người phê duyệt", "Approver"],
  cohort_manager: ["Quản lý khoá học", "Cohort manager"],
  training_manager: ["Quản lý đào tạo", "Training manager"],
  mentor: ["Mentor", "Mentor"],
  admin: ["Quản trị viên (IT)", "Administrator (IT)"],
  platform_admin: ["Quản trị nền tảng", "Platform admin"],
};

const COST_CATEGORIES: Record<string, Bi> = {
  stipend: ["Phụ cấp học viên", "Learner stipends"],
  ai: ["Chi phí AI", "AI costs"],
  infrastructure: ["Hạ tầng", "Infrastructure"],
  partner: ["Đối tác", "Partners"],
  operations: ["Vận hành", "Operations"],
  other: ["Khác", "Other"],
};

const SETTINGS: Record<string, Bi> = {
  usd_vnd_rate: ["Tỷ giá USD/VND", "USD/VND exchange rate"],
  ai_monthly_budget_usd: ["Trần chi phí AI hằng tháng (USD)", "Monthly AI budget cap (USD)"],
  ai_engine: ["Động cơ sàng lọc AI", "AI screening engine"],
  assistant_engine: ["Động cơ trợ lý hỏi đáp", "Q&A assistant engine"],
  stipend_vnd_per_month: ["Phụ cấp mỗi học viên mỗi tháng (VND)", "Monthly stipend per learner (VND)"],
  invite_ttl_hours: ["Thời hạn link lời mời (giờ)", "Invitation link lifetime (hours)"],
  microsoft_signup: ["Ứng viên tự đăng ký bằng Microsoft", "Applicant self-signup with Microsoft"],
  microsoft_allowed_tenants: ["Giới hạn tenant Microsoft được phép", "Allowed Microsoft tenants"],
};

const FIELDS: Record<string, Bi> = {
  "profile.full_name": ["Họ tên", "Full name"],
  "profile.phone": ["Số điện thoại", "Phone number"],
  "content.education": ["Học vấn", "Education"],
  "content.skills": ["Kỹ năng", "Skills"],
  "content.essays.motivation": ["Động lực", "Motivation"],
};

const EVENTS: Record<string, Bi> = {
  "application.created": ["Tạo hồ sơ", "Application created"],
  "application.submitted": ["Đã nộp hồ sơ", "Application submitted"],
  "status.in_round": ["Bắt đầu xét vòng đầu", "First round review started"],
  "round.advanced": ["Chuyển sang vòng tiếp theo", "Moved to the next round"],
  "info.requested": ["Cần bổ sung thông tin", "More information requested"],
  "application.info_provided": ["Đã bổ sung thông tin", "Information provided"],
  "decision.proposed": ["Có đề xuất quyết định, chờ phê duyệt", "Decision proposed, awaiting approval"],
  "decision.returned": ["Đề xuất được trả lại để xem xét thêm", "Proposal returned for further review"],
  "decision.accepted": ["Hồ sơ được nhận", "Application accepted"],
  "decision.rejected": ["Hồ sơ không đạt", "Application not accepted"],
  "decision.waitlisted": ["Vào danh sách dự bị", "Added to the waitlist"],
  "application.enrolled": ["Đã nhập học", "Enrolled"],
  "application.withdrawn": ["Đã rút hồ sơ", "Application withdrawn"],
  "round.started": ["Bắt đầu xét vòng đầu", "First round review started"],
};

const STATUS_UPDATED: Bi = ["Cập nhật trạng thái", "Status updated"];

export interface Labels {
  applicationStatus: (s: string | null | undefined) => Entry;
  intakeStatus: (s: string | null | undefined) => Entry;
  tier: (s: string | null | undefined) => Entry;
  outcome: (s: string | null | undefined) => Entry;
  enrollmentStatus: (s: string | null | undefined) => Entry;
  accountStatus: (s: string | null | undefined) => Entry;
  jobStatus: (s: string | null | undefined) => Entry;
  docStatus: (s: string | null | undefined) => Entry;
  suggestion: (s: string | null | undefined) => Entry;
  recommendation: (s: string | null | undefined) => Entry;
  role: (code: string) => string;
  costCategory: (code: string) => string;
  setting: (key: string) => string;
  field: (path: string) => string;
  event: (type: string) => string;
}

const cache = new Map<Locale, Labels>();

export function labels(locale: Locale): Labels {
  const hit = cache.get(locale);
  if (hit) return hit;
  const i = locale === "vi" ? 0 : 1;
  const status = (table: Table) => (s: string | null | undefined): Entry => {
    if (!s) return ["—", "info"];
    const row = table[s];
    return row ? [row[i], row[2]] : [s, "info"];
  };
  const text = (table: Record<string, Bi>) => (key: string) => table[key]?.[i] ?? key;
  const l: Labels = {
    applicationStatus: status(APPLICATION_STATUS),
    intakeStatus: status(INTAKE_STATUS),
    tier: status(TIER),
    outcome: status(OUTCOME),
    enrollmentStatus: status(ENROLLMENT_STATUS),
    accountStatus: status(ACCOUNT_STATUS),
    jobStatus: status(JOB_STATUS),
    docStatus: status(DOC_STATUS),
    suggestion: status(SUGGESTION),
    recommendation: status(RECOMMENDATION),
    role: text(ROLES),
    costCategory: text(COST_CATEGORIES),
    setting: text(SETTINGS),
    field: text(FIELDS),
    event: (type) => EVENTS[type]?.[i] ?? (type.startsWith("status.") ? STATUS_UPDATED[i] : type),
  };
  cache.set(locale, l);
  return l;
}

// ---- Bản tiếng Việt cho mã chưa chuyển sang useLabels() ----
const vi = labels("vi");
export const applicationStatus = vi.applicationStatus;
export const intakeStatus = vi.intakeStatus;
export const tierLabel = vi.tier;
export const outcomeLabel = vi.outcome;
export const enrollmentStatus = vi.enrollmentStatus;
export const accountStatus = vi.accountStatus;
export const jobStatus = vi.jobStatus;
export const docStatus = vi.docStatus;
export const suggestionLabel = vi.suggestion;
export const recommendationLabel = vi.recommendation;
export const eventLabel = vi.event;
const viTable = (table: Record<string, Bi>) => Object.fromEntries(Object.entries(table).map(([k, v]) => [k, v[0]]));
export const ROLE_LABELS: Record<string, string> = viTable(ROLES);
export const COST_CATEGORY_LABELS: Record<string, string> = viTable(COST_CATEGORIES);
export const SETTING_LABELS: Record<string, string> = viTable(SETTINGS);
export const FIELD_LABELS: Record<string, string> = viTable(FIELDS);
/** Danh sách mã (không kèm nhãn) để dựng ô chọn. */
export const ROLE_CODES = Object.keys(ROLES);
export const COST_CATEGORY_CODES = Object.keys(COST_CATEGORIES);
