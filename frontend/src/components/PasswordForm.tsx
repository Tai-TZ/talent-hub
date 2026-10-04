"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "./providers";
import { Alert } from "./ui/Alert";
import { Button } from "./ui/Button";
import { TextField } from "./ui/TextField";

export const MIN_PASSWORD_LENGTH = 10;

export function PasswordForm({ firstTime }: { firstTime: boolean }) {
  const { t } = useI18n();
  const router = useRouter();
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const current = String(form.get("current") ?? "");
    const next = String(form.get("next") ?? "");
    const confirm = String(form.get("confirm") ?? "");

    setError(null);
    setDone(false);
    if (next.length < MIN_PASSWORD_LENGTH) return setFieldError(t.password.tooShort);
    if (next !== confirm) return setFieldError(t.password.mismatch);
    setFieldError(null);

    setSubmitting(true);
    try {
      await api("/auth/password/change", { method: "POST", json: { current_password: current, new_password: next } });
      formEl.reset();
      setDone(true);
      if (firstTime) {
        router.replace("/dashboard");
        router.refresh();
      }
    } catch (err) {
      // 400 mang thông điệp cụ thể của máy chủ (sai mật khẩu hiện tại, vi phạm chính sách).
      setError(err instanceof ApiError ? err.message || t.common.genericError : t.common.networkError);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="th-card form-card stack" onSubmit={onSubmit} noValidate>
      {firstTime ? <Alert tone="warning">{t.password.firstTime}</Alert> : null}
      {error ? <Alert tone="danger">{error}</Alert> : null}
      {done ? <Alert tone="success">{t.password.success}</Alert> : null}
      <TextField label={t.password.current} name="current" type="password" autoComplete="current-password" required showLabel={t.login.showPassword} hideLabel={t.login.hidePassword} />
      <TextField
        label={t.password.next}
        name="next"
        type="password"
        autoComplete="new-password"
        required
        help={t.password.hint}
        error={fieldError ?? undefined}
        showLabel={t.login.showPassword}
        hideLabel={t.login.hidePassword}
      />
      <TextField label={t.password.confirm} name="confirm" type="password" autoComplete="new-password" required showLabel={t.login.showPassword} hideLabel={t.login.hidePassword} />
      <Button type="submit" loading={submitting}>
        {submitting ? t.password.submitting : t.password.submit}
      </Button>
    </form>
  );
}
