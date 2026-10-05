import { describe, expect, it } from "vitest";
import { computeTotal, fieldTexts, markSegments, snippetOf } from "@/features/staff/evidence";

const content = {
  education: [{ school: "Northwind University", degree: "Cử nhân", major: "Khoa học máy tính", status: "final_year", year: 2026, gpa: 8.7 }],
  experience: [{ org: "FPT", role: "Thực tập", years: 0.5, description: "Xây dựng API" }],
  projects: [{ title: "Chatbot", description: "Trả lời câu hỏi tuyển sinh", link: null, tech: ["Python", "FastAPI"] }],
  skills: ["Python", "SQL"],
  essays: { motivation: "Tôi muốn học AI ứng dụng.", problem_solving: "" },
  links: { github: null, linkedin: null, portfolio: null },
  cv_text: "",
  preferences: { tracks: [] },
};

describe("fieldTexts", () => {
  it("khớp quy tắc dựng văn bản của backend", () => {
    const f = fieldTexts(content);
    expect(f["education.0"]).toBe("Cử nhân Khoa học máy tính Northwind University (final_year, GPA 8.7)");
    expect(f["experience.0"]).toBe("Thực tập — FPT — Xây dựng API");
    expect(f["projects.0"]).toBe("Chatbot. Trả lời câu hỏi tuyển sinh Công nghệ: Python, FastAPI.");
    expect(f["skills"]).toBe("Python, SQL");
    expect(f["essays.motivation"]).toBe("Tôi muốn học AI ứng dụng.");
    expect(f).not.toHaveProperty("essays.problem_solving");
    expect(f).not.toHaveProperty("cv_text");
  });
});

describe("snippetOf", () => {
  it("trả ngữ cảnh quanh câu trích dẫn", () => {
    const s = snippetOf("Tôi đã xây dựng một chatbot cho trường và phục vụ 500 sinh viên mỗi ngày.", "chatbot cho trường", 10);
    expect(s).toEqual({ before: "… dựng một ", quote: "chatbot cho trường", after: " và phục v…" });
  });

  it("trả null khi văn bản đã đổi", () => {
    expect(snippetOf("nội dung khác", "chatbot")).toBeNull();
    expect(snippetOf(undefined, "chatbot")).toBeNull();
  });
});

describe("markSegments", () => {
  it("tô sáng và gộp các đoạn chồng nhau", () => {
    const segs = markSegments("abcdefghij", ["cde", "def", "ij"]);
    expect(segs).toEqual([
      { text: "ab", mark: false },
      { text: "cdef", mark: true },
      { text: "gh", mark: false },
      { text: "ij", mark: true },
    ]);
  });

  it("không có trích dẫn thì giữ nguyên văn bản", () => {
    expect(markSegments("xin chào", [])).toEqual([{ text: "xin chào", mark: false }]);
  });
});

describe("computeTotal", () => {
  const criteria = [
    { id: "a", weight: 3, max: 5 },
    { id: "b", weight: 1, max: 10 },
  ];

  it("tính điểm 0–100 theo trọng số, tiêu chí chưa chấm tính 0", () => {
    expect(computeTotal(criteria, { a: 5, b: 10 })).toBe(100);
    expect(computeTotal(criteria, { a: 5 })).toBe(75);
    expect(computeTotal(criteria, {})).toBe(0);
  });

  it("kẹp điểm vào khoảng hợp lệ", () => {
    expect(computeTotal(criteria, { a: 99, b: -4 })).toBe(75);
  });

  it("tổng trọng số bằng 0 thì trả 0", () => {
    expect(computeTotal([{ id: "a", weight: 0, max: 5 }], { a: 5 })).toBe(0);
  });
});
