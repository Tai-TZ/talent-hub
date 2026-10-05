import type { LabIntake } from "@/lib/contracts";

/** Số đợt tối đa một lần phân tích (khớp giới hạn của API). */
export const MAX_LAB_INTAKES = 10;

export type CriteriaGroup = {
  key: string;
  criteria: LabIntake["criteria"];
  intakes: LabIntake[];
  withOutcome: number;
};

const signature = (i: LabIntake) =>
  i.criteria
    .map((c) => c.id)
    .sort()
    .join("|");

/** Gom các đợt dùng cùng bộ tiêu chí; nhóm nhiều học viên có kết quả nhất đứng đầu. Đợt chưa có rubric bị bỏ. */
export function groupByCriteria(intakes: LabIntake[]): CriteriaGroup[] {
  const groups = new Map<string, CriteriaGroup>();
  for (const intake of intakes) {
    if (intake.criteria.length === 0) continue;
    const key = signature(intake);
    const group = groups.get(key) ?? { key, criteria: intake.criteria, intakes: [], withOutcome: 0 };
    group.intakes.push(intake);
    group.withOutcome += intake.with_outcome;
    groups.set(key, group);
  }
  return [...groups.values()]
    .map((g) => ({ ...g, intakes: [...g.intakes].sort((a, b) => b.with_outcome - a.with_outcome) }))
    .sort((a, b) => b.withOutcome - a.withOutcome || b.intakes.length - a.intakes.length);
}

/** Lựa chọn mặc định: các đợt (có kết quả khoá học) của nhóm tiêu chí nhiều dữ liệu nhất. */
export function defaultSelection(groups: CriteriaGroup[]): string[] {
  const best = groups[0];
  if (!best) return [];
  const withData = best.intakes.filter((i) => i.with_outcome > 0);
  return (withData.length > 0 ? withData : best.intakes).slice(0, MAX_LAB_INTAKES).map((i) => i.id);
}

/** Tiêu chí có ở mọi đợt đã chọn, theo thứ tự của đợt chọn đầu tiên (giống cách API ghép tiêu chí). */
export function commonCriteria(intakes: LabIntake[], selected: string[]): LabIntake["criteria"] {
  const chosen = selected.map((id) => intakes.find((i) => i.id === id)).filter((i): i is LabIntake => i != null);
  const [first, ...rest] = chosen;
  if (!first) return [];
  return first.criteria.filter((c) => rest.every((i) => i.criteria.some((x) => x.id === c.id)));
}
