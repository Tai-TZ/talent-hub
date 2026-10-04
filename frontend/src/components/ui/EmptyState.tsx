import type { ReactNode } from "react";

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="th-empty">
      <p className="th-type-h4">{title}</p>
      {children}
    </div>
  );
}
