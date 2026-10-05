import type { Tone } from "@/lib/labels";
import { Badge } from "./Badge";

/** Hiển thị cặp [nhãn, sắc thái] lấy từ lib/labels. */
export function StatusBadge({ entry }: { entry: readonly [label: string, tone: Tone] }) {
  return <Badge tone={entry[1]}>{entry[0]}</Badge>;
}
