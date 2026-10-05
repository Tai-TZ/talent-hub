import { describe, expect, it } from "vitest";
import { fmtAgo, fmtPct, fmtScore, fmtVndCompact, initials } from "@/lib/format";

describe("fmtVndCompact", () => {
  it("rút gọn theo tỷ và triệu", () => {
    expect(fmtVndCompact(11_745_000_000)).toBe("11,7 tỷ ₫");
    expect(fmtVndCompact(19_575_000)).toBe("19,6 triệu ₫");
  });

  it("giữ nguyên số nhỏ và xử lý giá trị rỗng", () => {
    expect(fmtVndCompact(250_000)).toContain("250.000");
    expect(fmtVndCompact(null)).toBe("—");
  });
});

describe("fmtPct / fmtScore", () => {
  it("định dạng tỉ lệ và điểm, rỗng thì hiện gạch ngang", () => {
    expect(fmtPct(0.756)).toBe("76%");
    expect(fmtPct(0.756, 1)).toBe("75.6%");
    expect(fmtPct(null)).toBe("—");
    expect(fmtScore(72.456)).toBe("72.5");
    expect(fmtScore(undefined)).toBe("—");
  });
});

describe("fmtAgo", () => {
  const now = new Date("2026-10-05T12:00:00Z");
  it("diễn đạt khoảng thời gian tương đối", () => {
    expect(fmtAgo("2026-10-05T11:59:50Z", now)).toBe("vừa xong");
    expect(fmtAgo("2026-10-05T11:30:00Z", now)).toBe("30 phút trước");
    expect(fmtAgo("2026-10-05T09:00:00Z", now)).toBe("3 giờ trước");
    expect(fmtAgo("2026-10-02T12:00:00Z", now)).toBe("3 ngày trước");
  });
});

describe("initials", () => {
  it("lấy chữ cái đầu của họ và tên", () => {
    expect(initials("Nguyễn Văn An")).toBe("NA");
    expect(initials("An")).toBe("A");
  });
});
