import { describe, expect, it } from "vitest";
import { initials } from "@/components/shell/UserMenu";
import { commonCriteria, defaultSelection, groupByCriteria, MAX_LAB_INTAKES } from "@/features/analytics/lab-selection";
import type { LabIntake } from "@/lib/contracts";

const crit = (...ids: string[]) => ids.map((id) => ({ id, name: id.toUpperCase() }));
const intake = (id: string, criteria: LabIntake["criteria"], with_outcome: number): LabIntake => ({
  id,
  name: `Đợt ${id}`,
  status: "closed",
  admitted: with_outcome + 5,
  with_outcome,
  criteria,
});

describe("Rubric Lab: chọn đợt theo bộ tiêu chí", () => {
  const demo = [intake("k1", crit("a", "b", "c"), 140), intake("k2", crit("c", "b", "a"), 150), intake("k4", crit("a", "b", "c"), 0)];
  const e2e = [intake("e1", crit("x", "y"), 0), intake("e2", crit("y", "x"), 0)];
  const noRubric = intake("n", [], 30);

  it("gom các đợt cùng bộ tiêu chí (không phụ thuộc thứ tự), nhóm nhiều dữ liệu đứng đầu, bỏ đợt chưa có rubric", () => {
    const groups = groupByCriteria([...e2e, noRubric, ...demo]);
    expect(groups.map((g) => g.intakes.map((i) => i.id))).toEqual([
      ["k2", "k1", "k4"],
      ["e1", "e2"],
    ]);
    expect(groups[0]?.withOutcome).toBe(290);
  });

  it("mặc định chỉ chọn các đợt có kết quả khoá học của nhóm tốt nhất, không lẫn đợt thử", () => {
    expect(defaultSelection(groupByCriteria([...e2e, ...demo]))).toEqual(["k2", "k1"]);
    expect(defaultSelection([])).toEqual([]);
    const many = Array.from({ length: 14 }, (_, i) => intake(`m${i}`, crit("a"), 10 + i));
    expect(defaultSelection(groupByCriteria(many))).toHaveLength(MAX_LAB_INTAKES);
  });

  it("tiêu chí chung theo thứ tự của đợt chọn đầu tiên; khác bộ thì rỗng", () => {
    const all = [...demo, ...e2e, intake("p", crit("b", "c", "z"), 9)];
    expect(commonCriteria(all, ["k2", "k1"]).map((c) => c.id)).toEqual(["c", "b", "a"]);
    expect(commonCriteria(all, ["k1", "p"]).map((c) => c.id)).toEqual(["b", "c"]);
    expect(commonCriteria(all, ["k1", "e1"])).toEqual([]);
    expect(commonCriteria(all, [])).toEqual([]);
  });
});

describe("chữ viết tắt trên avatar", () => {
  it("chỉ lấy chữ cái của từ đầu và từ cuối", () => {
    expect(initials("reviewer (northwind)")).toBe("RV");
    expect(initials("Nguyễn Minh Anh")).toBe("NA");
    expect(initials("Đặng")).toBe("Đ");
    expect(initials("  (123) ")).toBe("?");
  });
});
