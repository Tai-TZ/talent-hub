import { describe, expect, it } from "vitest";
import { resolveOrgSlug, safeNextPath } from "@/lib/org";

describe("safeNextPath", () => {
  it.each(["/dashboard", "/staff/queue?intake=1&round=portfolio", "/apply#step-2"])("giữ đường dẫn nội bộ %s", (path) => {
    expect(safeNextPath(path)).toBe(path);
  });

  it.each([
    ["rỗng", ""],
    ["null", null],
    ["tuyệt đối", "https://evil.com"],
    ["protocol-relative", "//evil.com"],
    ["gạch chéo ngược", "/\\evil.com"],
    ["tab bị URL parser bỏ qua", "/\t/evil.com"],
    ["xuống dòng", "/\n/evil.com"],
    ["carriage return", "/\r/evil.com"],
    ["ký tự DEL", "/\u007f/evil.com"],
    ["không bắt đầu bằng /", "evil.com"],
  ])("trả về mặc định khi %s", (_name, next) => {
    expect(safeNextPath(next)).toBe("/dashboard");
  });

  it("dùng fallback tuỳ chọn", () => {
    expect(safeNextPath("//evil.com", "/login")).toBe("/login");
  });
});

describe("resolveOrgSlug", () => {
  it("lấy slug từ tên miền con", () => {
    expect(resolveOrgSlug("scale.talenthub.example:443", "talenthub.example", "northwind")).toBe("scale");
  });

  it("dùng tổ chức mặc định khi host không khớp hoặc nhãn không hợp lệ", () => {
    expect(resolveOrgSlug("evil.com", "talenthub.example", "northwind")).toBe("northwind");
    expect(resolveOrgSlug("a.b.talenthub.example", "talenthub.example", "northwind")).toBe("northwind");
    expect(resolveOrgSlug("Bad_Slug.talenthub.example", "talenthub.example", "northwind")).toBe("northwind");
  });
});
