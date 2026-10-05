import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TextField } from "@/components/ui/TextField";

/** Mọi id trong aria-describedby phải trỏ tới một phần tử đang có trong DOM. */
function describedTargets(input: HTMLElement): (HTMLElement | null)[] {
  const ids = (input.getAttribute("aria-describedby") ?? "").split(" ").filter(Boolean);
  return ids.map((id) => document.getElementById(id));
}

describe("TextField", () => {
  it("chỉ tham chiếu phần trợ giúp khi không có lỗi", () => {
    render(<TextField label="Email" help="Dùng email công việc" />);
    const targets = describedTargets(screen.getByLabelText("Email"));
    expect(targets).toHaveLength(1);
    expect(targets[0]).toHaveTextContent("Dùng email công việc");
  });

  it("khi có lỗi thì chỉ tham chiếu thông báo lỗi, không trỏ tới phần trợ giúp đã ẩn", () => {
    render(<TextField label="Email" help="Dùng email công việc" error="Email không hợp lệ" />);
    const input = screen.getByLabelText("Email");
    const targets = describedTargets(input);
    expect(targets.every(Boolean)).toBe(true);
    expect(targets.map((el) => el?.textContent)).toEqual(["Email không hợp lệ"]);
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("không có trợ giúp lẫn lỗi thì không có aria-describedby", () => {
    render(<TextField label="Email" />);
    expect(screen.getByLabelText("Email")).not.toHaveAttribute("aria-describedby");
  });
});
