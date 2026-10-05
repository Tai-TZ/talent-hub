"use client";

import type { IntakeT } from "@/lib/contracts";
import { intakeStatus } from "@/lib/labels";
import { SelectField } from "./ui/Fields";

export function IntakePicker({ intakes, selected, onSelect }: { intakes: IntakeT[]; selected?: IntakeT; onSelect: (id: string) => void }) {
  return (
    <SelectField label="Đợt tuyển" value={selected?.id ?? ""} onChange={(e) => onSelect(e.target.value)} disabled={intakes.length === 0}>
      {intakes.map((i) => (
        <option key={i.id} value={i.id}>
          {i.name} · {intakeStatus(i.status)[0]}
        </option>
      ))}
    </SelectField>
  );
}
