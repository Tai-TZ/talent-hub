"use client";

import { useId, useState, type InputHTMLAttributes } from "react";
import { EyeIcon } from "../icons";

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  error?: string;
  help?: string;
  /** Chỉ dùng với type="password": nhãn cho nút hiện/ẩn mật khẩu. */
  showLabel?: string;
  hideLabel?: string;
}

export function TextField({ label, error, help, showLabel, hideLabel, type = "text", className, required, ...rest }: Props) {
  const id = useId();
  const helpId = `${id}-help`;
  const errorId = `${id}-error`;
  const [revealed, setRevealed] = useState(false);
  const isPassword = type === "password";
  // Khi có lỗi, phần trợ giúp bị ẩn: chỉ tham chiếu tới phần tử thực sự hiển thị.
  const describedBy = [help && !error ? helpId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div className="th-field">
      <label className="th-field__label" htmlFor={id}>
        {label}
        {required ? (
          <span className="th-field__required" aria-hidden="true">
            {" "}
            *
          </span>
        ) : null}
      </label>
      <div className="field-control">
        <input
          id={id}
          type={isPassword && revealed ? "text" : type}
          className={["th-input", error ? "th-input--error" : "", isPassword ? "field-control__input--has-action" : "", className]
            .filter(Boolean)
            .join(" ")}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          required={required}
          {...rest}
        />
        {isPassword && showLabel && hideLabel ? (
          <button
            type="button"
            className="field-control__action"
            onClick={() => setRevealed((v) => !v)}
            aria-label={revealed ? hideLabel : showLabel}
            aria-pressed={revealed}
          >
            <EyeIcon off={revealed} />
          </button>
        ) : null}
      </div>
      {help && !error ? (
        <span id={helpId} className="th-field__help">
          {help}
        </span>
      ) : null}
      {error ? (
        <span id={errorId} className="th-field__error">
          {error}
        </span>
      ) : null}
    </div>
  );
}
