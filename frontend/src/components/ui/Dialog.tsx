"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { CloseIcon } from "../icons";

interface Props {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
  closeLabel?: string;
}

/**
 * Hộp thoại dùng thẻ <dialog> gốc: trình duyệt lo bẫy tiêu điểm, phím Escape, nền bị vô hiệu và aria-modal.
 * Tiêu điểm trở lại nút đã mở hộp thoại khi đóng.
 */
export function Dialog({ open, title, onClose, children, footer, size = "md", closeLabel = "Đóng" }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={`dialog dialog--${size}`}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      {open ? (
        <div className="dialog__panel">
          <header className="dialog__header">
            <h2 id={titleId} className="th-type-h4">
              {title}
            </h2>
            <button type="button" className="icon-btn" onClick={onClose} aria-label={closeLabel}>
              <CloseIcon size={22} />
            </button>
          </header>
          <div className="dialog__body">{children}</div>
          {footer ? <footer className="dialog__footer">{footer}</footer> : null}
        </div>
      ) : null}
    </dialog>
  );
}
