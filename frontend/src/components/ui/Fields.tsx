"use client";

import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

interface Base {
  label: string;
  error?: string;
  help?: string;
}

function Wrapper({ label, error, help, id, required, children }: Base & { id: string; required?: boolean; children: ReactNode }) {
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
      {children}
      {help && !error ? (
        <span id={`${id}-help`} className="th-field__help">
          {help}
        </span>
      ) : null}
      {error ? (
        <span id={`${id}-error`} className="th-field__error">
          {error}
        </span>
      ) : null}
    </div>
  );
}

function describedBy(id: string, help?: string, error?: string) {
  return [help && !error ? `${id}-help` : null, error ? `${id}-error` : null].filter(Boolean).join(" ") || undefined;
}

export function TextArea({ label, error, help, className, required, ...rest }: Base & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id">) {
  const id = useId();
  return (
    <Wrapper label={label} error={error} help={help} id={id} required={required}>
      <textarea
        id={id}
        className={["th-textarea", error ? "th-textarea--error" : "", className].filter(Boolean).join(" ")}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, help, error)}
        required={required}
        {...rest}
      />
    </Wrapper>
  );
}

export function SelectField({
  label,
  error,
  help,
  className,
  required,
  children,
  ...rest
}: Base & Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> & { children: ReactNode }) {
  const id = useId();
  return (
    <Wrapper label={label} error={error} help={help} id={id} required={required}>
      <select
        id={id}
        className={["th-select", error ? "th-select--error" : "", className].filter(Boolean).join(" ")}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, help, error)}
        required={required}
        {...rest}
      >
        {children}
      </select>
    </Wrapper>
  );
}

export function Checkbox({ label, ...rest }: { label: ReactNode } & Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  return (
    <label className="th-check">
      <input type="checkbox" {...rest} />
      <span>{label}</span>
    </label>
  );
}

export function Range({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
  help,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  format?: (value: number) => string;
  help?: string;
}) {
  const id = useId();
  return (
    <div className="th-field">
      <label className="th-field__label range__label" htmlFor={id}>
        <span>{label}</span>
        <output htmlFor={id}>{format ? format(value) : value}</output>
      </label>
      <input id={id} type="range" className="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      {help ? <span className="th-field__help">{help}</span> : null}
    </div>
  );
}
