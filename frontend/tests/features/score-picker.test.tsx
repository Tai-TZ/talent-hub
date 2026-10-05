import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { ScorePicker } from "@/features/staff/ReviewPanel";

function Harness({ initial }: { initial?: number }) {
  const [value, setValue] = useState<number | undefined>(initial);
  return <ScorePicker name="c1" label="Kinh nghiệm" max={20} value={value} onChange={setValue} />;
}

describe("ScorePicker dạng ô nhập số (thang > 10)", () => {
  it("xoá hết số thì về 'chưa chấm' để gõ lại được", () => {
    render(<Harness initial={7.5} />);
    const input = screen.getByLabelText("Điểm Kinh nghiệm (0 đến 20)");
    expect(input).toHaveValue(7.5);
    fireEvent.change(input, { target: { value: "" } });
    expect(input).toHaveValue(null);
    expect(screen.getByText("chưa chấm")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "6" } });
    expect(input).toHaveValue(6);
    expect(screen.getByText("6/20")).toBeInTheDocument();
  });

  it("kẹp điểm trong khoảng 0..max", () => {
    render(<Harness />);
    const input = screen.getByLabelText("Điểm Kinh nghiệm (0 đến 20)");
    fireEvent.change(input, { target: { value: "25" } });
    expect(input).toHaveValue(20);
  });
});
