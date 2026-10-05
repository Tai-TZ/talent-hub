import { describe, expect, it } from "vitest";
import { DEFAULT_RUBRIC, slugify, uniqueKey } from "@/features/intakes/templates";

describe("slugify", () => {
  it("bỏ dấu tiếng Việt và dùng snake_case", () => {
    expect(slugify("Xét hồ sơ")).toBe("xet_ho_so");
    expect(slugify("Đánh giá năng lực")).toBe("danh_gia_nang_luc");
    expect(slugify("  Phỏng vấn - vòng 2 ")).toBe("phong_van_vong_2");
  });

  it("luôn bắt đầu bằng chữ cái và không rỗng", () => {
    expect(slugify("2024 tuyển sinh")).toMatch(/^[a-z]/);
    expect(slugify("!!!", "vong")).toBe("vong");
  });

  it("giới hạn độ dài khớp quy tắc của backend (tối đa 40 ký tự)", () => {
    expect(slugify("a".repeat(100)).length).toBeLessThanOrEqual(39);
  });
});

describe("uniqueKey", () => {
  it("thêm hậu tố khi trùng", () => {
    expect(uniqueKey("vong", ["khac"])).toBe("vong");
    expect(uniqueKey("vong", ["vong"])).toBe("vong_2");
    expect(uniqueKey("vong", ["vong", "vong_2"])).toBe("vong_3");
  });
});

describe("DEFAULT_RUBRIC", () => {
  it("có khoá hợp lệ với backend và không trùng", () => {
    const ids = DEFAULT_RUBRIC.map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const id of ids) expect(id).toMatch(/^[a-z][a-z0-9_]{1,39}$/);
  });
});
