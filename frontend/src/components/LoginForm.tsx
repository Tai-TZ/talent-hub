"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import type { Me } from "@/lib/types";
import { useI18n } from "./providers";
import { Alert } from "./ui/Alert";
import { Button } from "./ui/Button";
import { TextField } from "./ui/TextField";

export function LoginForm({ next }: { next: string }) {
  const { t } = useI18n();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");
    if (!email || !password) {
      setError(t.login.required);
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      const me = await api<Me>("/auth/login", { method: "POST", json: { email, password } });
      router.replace(me.must_change_password ? "/account/password?first=1" : next);
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 401 ? t.login.invalid : err.status === 429 ? t.login.rateLimited : t.common.genericError);
      } else {
        setError(t.common.networkError);
      }
      setSubmitting(false);
    }
  }

  return (
    <form className="th-card th-card--feature auth__card" onSubmit={onSubmit} noValidate>
      <div className="stack">
        <h2 className="th-type-h3">{t.login.title}</h2>
        <p className="page-head__subtitle">{t.login.subtitle}</p>
      </div>
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <TextField label={t.login.email} name="email" type="email" autoComplete="username" inputMode="email" autoFocus required />
      <TextField
        label={t.login.password}
        name="password"
        type="password"
        autoComplete="current-password"
        showLabel={t.login.showPassword}
        hideLabel={t.login.hidePassword}
        required
      />
      <Button type="submit" size="lg" block loading={submitting}>
        {submitting ? t.login.submitting : t.login.submit}
      </Button>
    </form>
  );
}
