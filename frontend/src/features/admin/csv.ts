export interface ImportRow {
  email: string;
  full_name: string;
  roles: string[];
}

export interface ParsedCsv {
  rows: ImportRow[];
  /** Dòng không đọc được (số thứ tự dòng trong văn bản gốc, thông báo). */
  problems: { line: number; message: string }[];
}

/** Tách một dòng CSV có hỗ trợ dấu ngoặc kép ("a, b") và "" thoát dấu ngoặc. */
function splitLine(line: string, delimiter: string): string[] {
  const out: string[] = [];
  let current = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]!;
    if (quoted) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i++;
      } else if (ch === '"') quoted = false;
      else current += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === delimiter) {
      out.push(current.trim());
      current = "";
    } else current += ch;
  }
  out.push(current.trim());
  return out;
}

/**
 * Đọc danh sách tài khoản: mỗi dòng `email, họ tên, vai trò` (vai trò cách nhau bằng `;` hoặc `|`).
 * Hỗ trợ dòng tiêu đề, dấu phân cách `,` hoặc `;` hoặc tab (dán từ Excel). Dòng trống được bỏ qua.
 */
export function parseAccountsCsv(text: string, defaultRole = "reviewer"): ParsedCsv {
  const lines = text.replace(/^﻿/, "").split(/\r?\n/);
  const rows: ImportRow[] = [];
  const problems: ParsedCsv["problems"] = [];
  const sample = lines.find((l) => l.trim()) ?? "";
  const delimiter = sample.includes("\t") ? "\t" : sample.split(",").length >= sample.split(";").length ? "," : ";";

  lines.forEach((raw, index) => {
    if (!raw.trim()) return;
    const cells = splitLine(raw, delimiter);
    if (index === lines.findIndex((l) => l.trim()) && /^e-?mail$/i.test(cells[0] ?? "")) return; // dòng tiêu đề
    const [email = "", fullName = "", rolesRaw = ""] = cells;
    if (!email.includes("@")) {
      problems.push({ line: index + 1, message: "Thiếu địa chỉ email hợp lệ" });
      return;
    }
    if (!fullName) {
      problems.push({ line: index + 1, message: "Thiếu họ tên" });
      return;
    }
    const roles = rolesRaw
      .split(/[;|]/)
      .map((r) => r.trim().toLowerCase())
      .filter(Boolean);
    rows.push({ email, full_name: fullName, roles: roles.length ? roles : [defaultRole] });
  });
  return { rows, problems };
}
