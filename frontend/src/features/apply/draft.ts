import type { ApplicationView } from "@/lib/contracts";

/** Dữ liệu nháp phía người dùng. Dòng chưa đủ trường bắt buộc vẫn giữ trong form nhưng chưa gửi lên BE. */
export interface Draft {
  profile: {
    full_name: string;
    phone: string;
    date_of_birth: string;
    gender: string;
    city: string;
  };
  education: { school: string; degree: string; major: string; status: string; year: string; gpa: string }[];
  experience: { org: string; role: string; years: string; description: string }[];
  projects: { title: string; description: string; link: string; tech: string }[];
  skills: string;
  links: { github: string; linkedin: string; portfolio: string };
  cv_text: string;
  essays: { motivation: string; problem_solving: string };
  tracks: string[];
}

export const STEPS = [
  { key: "profile", label: "Thông tin cá nhân" },
  { key: "education", label: "Học vấn" },
  { key: "work", label: "Kinh nghiệm và dự án" },
  { key: "skills", label: "Kỹ năng và liên kết" },
  { key: "essays", label: "Bài luận và nguyện vọng" },
  { key: "review", label: "Xem lại và nộp" },
] as const;

export type StepKey = (typeof STEPS)[number]["key"];

export function emptyDraft(): Draft {
  return {
    profile: { full_name: "", phone: "", date_of_birth: "", gender: "", city: "" },
    education: [],
    experience: [],
    projects: [],
    skills: "",
    links: { github: "", linkedin: "", portfolio: "" },
    cv_text: "",
    essays: { motivation: "", problem_solving: "" },
    tracks: [],
  };
}

export function draftFromView(view: ApplicationView): Draft {
  const d = emptyDraft();
  const p = view.profile;
  if (p) {
    d.profile = {
      full_name: p.full_name ?? "",
      phone: p.phone ?? "",
      date_of_birth: p.date_of_birth ?? "",
      gender: p.gender ?? "",
      city: p.city ?? "",
    };
  }
  const c = view.content;
  d.education = c.education.map((e) => ({
    school: e.school ?? "",
    degree: e.degree ?? "",
    major: e.major ?? "",
    status: e.status ?? "student",
    year: e.year != null ? String(e.year) : "",
    gpa: e.gpa != null ? String(e.gpa) : "",
  }));
  d.experience = c.experience.map((e) => ({
    org: e.org ?? "",
    role: e.role ?? "",
    years: e.years ? String(e.years) : "",
    description: e.description ?? "",
  }));
  d.projects = c.projects.map((x) => ({
    title: x.title ?? "",
    description: x.description ?? "",
    link: x.link ?? "",
    tech: (x.tech ?? []).join(", "),
  }));
  d.skills = c.skills.join(", ");
  d.links = { github: c.links.github ?? "", linkedin: c.links.linkedin ?? "", portfolio: c.links.portfolio ?? "" };
  d.cv_text = c.cv_text ?? "";
  d.essays = { motivation: c.essays.motivation ?? "", problem_solving: c.essays.problem_solving ?? "" };
  d.tracks = c.preferences.tracks ?? [];
  return d;
}

const splitList = (value: string) =>
  value
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean);

const optional = (value: string) => (value.trim() === "" ? undefined : value.trim());
const optionalNumber = (value: string) => {
  const n = Number(value.replace(",", "."));
  return value.trim() === "" || Number.isNaN(n) ? undefined : n;
};

/** Chuyển nháp thành payload PATCH. Dòng thiếu trường bắt buộc (trường, tổ chức, tên dự án) bị bỏ qua. */
export function toPayload(d: Draft) {
  return {
    profile: {
      full_name: d.profile.full_name.trim(),
      phone: optional(d.profile.phone),
      date_of_birth: optional(d.profile.date_of_birth),
      gender: optional(d.profile.gender),
      city: optional(d.profile.city),
    },
    content: {
      education: d.education
        .filter((e) => e.school.trim())
        .map((e) => ({
          school: e.school.trim(),
          degree: e.degree.trim(),
          major: e.major.trim(),
          status: e.status,
          year: optionalNumber(e.year),
          gpa: optionalNumber(e.gpa),
        })),
      experience: d.experience
        .filter((e) => e.org.trim())
        .map((e) => ({
          org: e.org.trim(),
          role: e.role.trim(),
          years: optionalNumber(e.years) ?? 0,
          description: e.description.trim(),
        })),
      projects: d.projects
        .filter((x) => x.title.trim())
        .map((x) => ({
          title: x.title.trim(),
          description: x.description.trim(),
          link: optional(x.link),
          tech: splitList(x.tech),
        })),
      skills: splitList(d.skills),
      links: { github: optional(d.links.github), linkedin: optional(d.links.linkedin), portfolio: optional(d.links.portfolio) },
      cv_text: d.cv_text.trim(),
      essays: { motivation: d.essays.motivation.trim(), problem_solving: d.essays.problem_solving.trim() },
      preferences: { tracks: d.tracks },
    },
  };
}

/** Bước chứa trường lỗi, để dẫn người dùng tới đúng chỗ cần sửa. */
export function stepOfField(path: string): StepKey {
  if (path.startsWith("profile")) return "profile";
  if (path.startsWith("content.education")) return "education";
  if (path.startsWith("content.experience") || path.startsWith("content.projects")) return "work";
  if (path.startsWith("content.skills") || path.startsWith("content.links") || path.startsWith("content.cv_text")) return "skills";
  return "essays";
}

export const MIN_ESSAY_CHARS = 200;
