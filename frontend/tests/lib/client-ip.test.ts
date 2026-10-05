import { describe, expect, it } from "vitest";
import { clientIpFrom } from "@/lib/client-ip";

describe("clientIpFrom", () => {
  it("lấy IP do proxy tin cậy nối vào cuối, không lấy mục client tự đặt ở đầu", () => {
    expect(clientIpFrom("6.6.6.6, 203.0.113.7", 1)).toBe("203.0.113.7");
    expect(clientIpFrom("6.6.6.6, 203.0.113.7, 10.0.0.2", 2)).toBe("203.0.113.7");
  });

  it("dùng IP socket mà Next tự điền khi không có proxy", () => {
    expect(clientIpFrom("127.0.0.1", 1)).toBe("127.0.0.1");
    expect(clientIpFrom("::ffff:127.0.0.1", 1)).toBe("::ffff:127.0.0.1");
  });

  it("không vượt quá đầu danh sách khi số hop lớn hơn số mục", () => {
    expect(clientIpFrom("203.0.113.7", 3)).toBe("203.0.113.7");
  });

  it("bỏ giá trị rỗng hoặc không giống IP", () => {
    expect(clientIpFrom(null, 1)).toBeNull();
    expect(clientIpFrom(" , ", 1)).toBeNull();
    expect(clientIpFrom("1.2.3.4, <script>", 1)).toBeNull();
  });

  it("coi số hop không hợp lệ là 1", () => {
    expect(clientIpFrom("6.6.6.6, 203.0.113.7", Number.NaN)).toBe("203.0.113.7");
    expect(clientIpFrom("6.6.6.6, 203.0.113.7", 0)).toBe("203.0.113.7");
  });
});
