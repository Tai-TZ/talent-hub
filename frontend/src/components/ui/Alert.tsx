import type { ReactNode } from "react";
import { CheckIcon, CircleInfoIcon, TriangleExclamationIcon } from "../icons";

type Tone = "info" | "success" | "warning" | "danger";

const ICONS = { info: CircleInfoIcon, success: CheckIcon, warning: TriangleExclamationIcon, danger: TriangleExclamationIcon };

/** `danger` dùng role="alert" (khẩn); các mức còn lại dùng role="status" (thông báo lịch sự). */
export function Alert({ tone = "info", title, children }: { tone?: Tone; title?: string; children: ReactNode }) {
  const Icon = ICONS[tone];
  return (
    <div className={`th-alert th-alert--${tone} alert`} role={tone === "danger" ? "alert" : "status"}>
      <Icon size={18} className="alert__icon" />
      <div className="th-alert__body">
        {title ? <div className="th-alert__title">{title}</div> : null}
        <div className="th-alert__content">{children}</div>
      </div>
    </div>
  );
}
