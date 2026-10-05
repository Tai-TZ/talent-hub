import type { ApplicationView, Criterion } from "@/lib/contracts";

type Content = ApplicationView["content"];

/**
 * Dựng lại đúng văn bản từng trường mà AI đã đọc (cùng quy tắc với backend/src/ai/text.py::build_fields),
 * để vị trí trích dẫn bằng chứng khớp và có thể hiển thị kèm ngữ cảnh.
 */
export function fieldTexts(content: Content): Record<string, string> {
  const out: Record<string, string> = {};
  if (content.essays.motivation) out["essays.motivation"] = content.essays.motivation;
  if (content.essays.problem_solving) out["essays.problem_solving"] = content.essays.problem_solving;
  content.education.forEach((e, i) => {
    const text = [e.degree, e.major, e.school].filter(Boolean).join(" ");
    const gpa = e.gpa != null ? `, GPA ${e.gpa}` : "";
    out[`education.${i}`] = `${text} (${e.status}${gpa})`.trim();
  });
  content.experience.forEach((e, i) => {
    out[`experience.${i}`] = [e.role, e.org, e.description].filter(Boolean).join(" — ");
  });
  content.projects.forEach((p, i) => {
    const tech = p.tech.length ? ` Công nghệ: ${p.tech.join(", ")}.` : "";
    out[`projects.${i}`] = `${p.title}. ${p.description}${tech}`.trim();
  });
  if (content.skills.length) out["skills"] = content.skills.join(", ");
  if (content.cv_text) out["cv_text"] = content.cv_text;
  return out;
}

export function fieldLabel(key: string): string {
  const [name, index] = key.split(".");
  const n = index !== undefined ? ` ${Number(index) + 1}` : "";
  switch (name) {
    case "essays":
      return index === "motivation" ? "Bài luận: động lực" : "Bài luận: giải quyết vấn đề";
    case "education":
      return `Học vấn${n}`;
    case "experience":
      return `Kinh nghiệm${n}`;
    case "projects":
      return `Dự án${n}`;
    case "skills":
      return "Kỹ năng";
    case "cv_text":
      return "Nội dung CV";
    default:
      return key;
  }
}

export interface Snippet {
  before: string;
  quote: string;
  after: string;
}

/** Trích đoạn có ngữ cảnh quanh câu trích dẫn; null nếu không tìm thấy (văn bản đã đổi sau khi AI đọc). */
export function snippetOf(text: string | undefined, quote: string, radius = 70): Snippet | null {
  if (!text) return null;
  const haystack = text.normalize("NFC");
  const needle = quote.normalize("NFC");
  const at = haystack.indexOf(needle);
  if (at < 0) return null;
  const from = Math.max(0, at - radius);
  const to = Math.min(haystack.length, at + needle.length + radius);
  return {
    before: (from > 0 ? "…" : "") + haystack.slice(from, at),
    quote: needle,
    after: haystack.slice(at + needle.length, to) + (to < haystack.length ? "…" : ""),
  };
}

/** Tách văn bản thành các đoạn có/không được tô sáng theo danh sách câu trích dẫn. */
export function markSegments(text: string, quotes: string[]): { text: string; mark: boolean }[] {
  const haystack = text.normalize("NFC");
  const ranges: [number, number][] = [];
  for (const quote of quotes) {
    const needle = quote.normalize("NFC");
    const at = needle ? haystack.indexOf(needle) : -1;
    if (at >= 0) ranges.push([at, at + needle.length]);
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const [start, end] of ranges) {
    const last = merged.at(-1);
    if (last && start <= last[1]) last[1] = Math.max(last[1], end);
    else merged.push([start, end]);
  }
  const out: { text: string; mark: boolean }[] = [];
  let cursor = 0;
  for (const [start, end] of merged) {
    if (start > cursor) out.push({ text: haystack.slice(cursor, start), mark: false });
    out.push({ text: haystack.slice(start, end), mark: true });
    cursor = end;
  }
  if (cursor < haystack.length) out.push({ text: haystack.slice(cursor), mark: false });
  return out.length ? out : [{ text: haystack, mark: false }];
}

/** Điểm tổng 0–100 theo trọng số (cùng công thức backend/src/services/reviews.py::compute_total). */
export function computeTotal(criteria: Pick<Criterion, "id" | "weight" | "max">[], scores: Record<string, number>): number {
  const weightSum = criteria.reduce((sum, c) => sum + c.weight, 0);
  if (weightSum <= 0) return 0;
  const achieved = criteria.reduce((sum, c) => {
    const value = Math.min(Math.max(scores[c.id] ?? 0, 0), c.max);
    return sum + (value / c.max) * c.weight;
  }, 0);
  return Math.round((achieved / weightSum) * 10000) / 100;
}
