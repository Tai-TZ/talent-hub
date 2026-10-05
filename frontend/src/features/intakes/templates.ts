/** Mẫu cấu hình đợt tuyển: người dùng chỉnh lại được, khoá nội bộ sinh tự động từ tên. */

export interface RoundDraft {
  key: string;
  label: string;
  type: "review" | "assessment" | "interview";
}

export interface CriterionDraft {
  id: string;
  name: string;
  description: string;
  weight: number;
  max: number;
  kind: string;
}

export const CRITERION_KINDS: { value: string; label: string }[] = [
  { value: "projects", label: "Dự án" },
  { value: "programming", label: "Lập trình" },
  { value: "ai_ml", label: "Nền tảng AI/ML" },
  { value: "data", label: "Dữ liệu" },
  { value: "education", label: "Học vấn" },
  { value: "experience", label: "Kinh nghiệm" },
  { value: "motivation", label: "Động lực" },
  { value: "problem_solving", label: "Giải quyết vấn đề" },
  { value: "communication", label: "Giao tiếp" },
  { value: "custom", label: "Khác (người chấm tự đánh giá)" },
];

export const ROUND_TYPES: { value: RoundDraft["type"]; label: string }[] = [
  { value: "review", label: "Xét hồ sơ" },
  { value: "assessment", label: "Bài đánh giá" },
  { value: "interview", label: "Phỏng vấn" },
];

export const DEFAULT_ROUNDS: RoundDraft[] = [
  { key: "portfolio", label: "Xét hồ sơ", type: "review" },
  { key: "aptitude", label: "Đánh giá năng lực", type: "assessment" },
];

export const DEFAULT_RUBRIC: CriterionDraft[] = [
  { id: "projects", name: "Dự án thực tế", description: "Dự án có sản phẩm, liên kết và kết quả đo được", weight: 3, max: 5, kind: "projects" },
  { id: "programming", name: "Lập trình", description: "Độ rộng và chiều sâu kỹ năng lập trình", weight: 3, max: 5, kind: "programming" },
  { id: "ai_ml", name: "Nền tảng AI/ML", description: "Hiểu biết và ứng dụng học máy", weight: 2, max: 5, kind: "ai_ml" },
  { id: "education", name: "Học vấn", description: "Ngành học, kết quả học tập", weight: 1, max: 5, kind: "education" },
  { id: "experience", name: "Kinh nghiệm", description: "Thực tập hoặc làm việc liên quan", weight: 1, max: 5, kind: "experience" },
  { id: "motivation", name: "Động lực", description: "Mức độ rõ ràng và cụ thể của động lực", weight: 1.5, max: 5, kind: "motivation" },
  { id: "communication", name: "Giao tiếp", description: "Cách trình bày mạch lạc", weight: 1, max: 5, kind: "communication" },
];

export interface EligibilityDraft {
  id: string;
  label: string;
  type: "education_status_in" | "min_skills" | "min_projects" | "min_essay_chars";
  values: string[];
  value: number | null;
}

export const ELIGIBILITY_PRESETS: EligibilityDraft[] = [
  { id: "status", label: "Đang học hoặc đã tốt nghiệp đại học", type: "education_status_in", values: ["student", "final_year", "graduated"], value: null },
  { id: "skills", label: "Khai ít nhất 3 kỹ năng", type: "min_skills", values: [], value: 3 },
  { id: "projects", label: "Có ít nhất 1 dự án", type: "min_projects", values: [], value: 1 },
  { id: "essay", label: "Bài luận động lực tối thiểu 400 ký tự", type: "min_essay_chars", values: [], value: 400 },
];

const VI_MAP: Record<string, string> = { đ: "d", Đ: "d" };

/** Chuyển tên tiếng Việt thành khoá ASCII dạng snake_case ("Xét hồ sơ" → "xet_ho_so"), bắt đầu bằng chữ cái. */
export function slugify(text: string, fallback = "muc"): string {
  const ascii = text
    .replace(/[đĐ]/g, (c) => VI_MAP[c] ?? c)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  const base = /^[a-z]/.test(ascii) ? ascii : `${fallback}_${ascii}`.replace(/_+$/, "");
  return base.slice(0, 39) || fallback;
}

/** Khoá duy nhất trong tập `taken`: thêm hậu tố _2, _3... khi trùng. */
export function uniqueKey(base: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  if (!used.has(base)) return base;
  for (let i = 2; i < 100; i++) {
    const candidate = `${base.slice(0, 36)}_${i}`;
    if (!used.has(candidate)) return candidate;
  }
  return `${base.slice(0, 30)}_${Date.now() % 100000}`;
}
