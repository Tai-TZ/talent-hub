import type { ReactNode } from "react";

export function Badge({ tone = "info", children }: { tone?: "info" | "success" | "warning" | "danger"; children: ReactNode }) {
  return <span className={`th-badge th-badge--${tone}`}>{children}</span>;
}
