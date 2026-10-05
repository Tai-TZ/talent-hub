import { describe, expect, it } from "vitest";
import { parseAccountsCsv } from "@/features/admin/csv";

describe("parseAccountsCsv", () => {
  it("đọc dòng tiêu đề, nhiều vai trò và dấu ngoặc kép", () => {
    const { rows, problems } = parseAccountsCsv('email,họ tên,vai trò\nan@x.edu,"Nguyễn, Văn An",reviewer;mentor\nbinh@x.edu,Trần Bình,approver');
    expect(problems).toEqual([]);
    expect(rows).toEqual([
      { email: "an@x.edu", full_name: "Nguyễn, Văn An", roles: ["reviewer", "mentor"] },
      { email: "binh@x.edu", full_name: "Trần Bình", roles: ["approver"] },
    ]);
  });

  it("nhận dữ liệu dán từ Excel (tab) và vai trò mặc định", () => {
    const { rows } = parseAccountsCsv("an@x.edu\tNguyễn An\t\r\nbinh@x.edu\tTrần Bình\tmentor", "reviewer");
    expect(rows).toEqual([
      { email: "an@x.edu", full_name: "Nguyễn An", roles: ["reviewer"] },
      { email: "binh@x.edu", full_name: "Trần Bình", roles: ["mentor"] },
    ]);
  });

  it("nhận dấu chấm phẩy làm phân cách và bỏ dòng trống", () => {
    const { rows } = parseAccountsCsv("\nan@x.edu;Nguyễn An;mentor\n\n");
    expect(rows).toHaveLength(1);
    expect(rows[0]?.roles).toEqual(["mentor"]);
  });

  it("báo lỗi dòng thiếu email hoặc họ tên kèm số dòng", () => {
    const { rows, problems } = parseAccountsCsv("khong-co-email,Tên,mentor\nan@x.edu,,mentor\nok@x.edu,Ổn,mentor");
    expect(rows.map((r) => r.email)).toEqual(["ok@x.edu"]);
    expect(problems).toEqual([
      { line: 1, message: "Thiếu địa chỉ email hợp lệ" },
      { line: 2, message: "Thiếu họ tên" },
    ]);
  });

  it("bỏ ký tự BOM đầu tệp", () => {
    expect(parseAccountsCsv("﻿email,họ tên\nan@x.edu,An").rows).toHaveLength(1);
  });
});
