"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import type { InvitationPreview } from "@/lib/contracts";
import type { Me } from "@/lib/types";
import { Alert } from "./ui/Alert";
import { Button } from "./ui/Button";
import { MicrosoftMark } from "./icons";
import { Skeleton } from "./ui/Skeleton";
import { TextField } from "./ui/TextField";

const MIN_PASSWORD_LENGTH = 10;
const SHOW = "Hiện mật khẩu";
const HIDE = "Ẩn mật khẩu";

function Form({ token, preview, microsoft }: { token: string; preview: InvitationPreview; microsoft: boolean }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const isReset = preview.kind === "reset";
  // Người đã có tài khoản ở tổ chức khác phải nhập đúng mật khẩu hiện có; không được đặt mật khẩu mới qua lời mời.
  const existing = preview.has_password;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    const confirm = String(form.get("confirm") ?? "");
    setError(null);
    if (!existing) {
      if (password.length < MIN_PASSWORD_LENGTH) return setFieldError(`Mật khẩu cần ít nhất ${MIN_PASSWORD_LENGTH} ký tự.`);
      if (password !== confirm) return setFieldError("Hai mật khẩu chưa khớp.");
    }
    setFieldError(null);
    setSubmitting(true);
    try {
      await api<Me>("/auth/invitations/accept", { method: "POST", json: { token, password } });
      router.replace("/dashboard");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message || "Không thể hoàn tất. Vui lòng thử lại." : "Không kết nối được máy chủ.");
      setSubmitting(false);
    }
  }

  return (
    <form className="th-card th-card--feature auth__card" onSubmit={onSubmit} noValidate>
      <div className="stack">
        <h1 className="th-type-h3">{isReset ? "Đặt lại mật khẩu" : `Chào mừng đến ${preview.organization}`}</h1>
        <p className="page-head__subtitle">
          Tài khoản <strong>{preview.email}</strong>
          {existing ? ": bạn đã có mật khẩu cho tài khoản này. Nhập mật khẩu hiện tại để tham gia tổ chức." : isReset ? ": tạo mật khẩu mới." : ": tạo mật khẩu để bắt đầu."}
        </p>
      </div>
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <TextField
        label={existing ? "Mật khẩu hiện tại" : "Mật khẩu mới"}
        name="password"
        type="password"
        autoComplete={existing ? "current-password" : "new-password"}
        required
        autoFocus
        help={existing ? undefined : `Ít nhất ${MIN_PASSWORD_LENGTH} ký tự và không chứa tên tài khoản email.`}
        error={existing ? undefined : (fieldError ?? undefined)}
        showLabel={SHOW}
        hideLabel={HIDE}
      />
      {existing ? null : <TextField label="Nhập lại mật khẩu" name="confirm" type="password" autoComplete="new-password" required showLabel={SHOW} hideLabel={HIDE} />}
      <Button type="submit" size="lg" block loading={submitting}>
        {isReset ? "Đặt mật khẩu" : "Kích hoạt tài khoản"}
      </Button>
      {microsoft && !isReset ? (
        <>
          <p className="auth__or" aria-hidden="true">
            hoặc
          </p>
          <a className="th-button th-button--secondary th-button--lg th-button--block" href={`/api/v1/auth/microsoft/start?mode=invite&token=${encodeURIComponent(token)}`}>
            <MicrosoftMark />
            Kích hoạt bằng tài khoản Microsoft
          </a>
        </>
      ) : null}
    </form>
  );
}

export function InviteForm({ token, microsoft = false }: { token: string; microsoft?: boolean }) {
  const preview = useQuery<InvitationPreview, ApiError>({
    queryKey: ["invite", token],
    queryFn: () => api<InvitationPreview>(`/auth/invitations/${encodeURIComponent(token)}`),
    retry: false,
    staleTime: Infinity,
  });

  if (preview.isPending) return <Skeleton lines={3} />;
  if (preview.isError) {
    return (
      <div className="th-card th-card--feature auth__card stack">
        <h1 className="th-type-h3">Liên kết không dùng được</h1>
        <Alert tone="danger">{preview.error.status === 429 ? "Thao tác quá nhanh, vui lòng thử lại sau ít phút." : "Liên kết đã hết hạn, đã được sử dụng hoặc không hợp lệ."}</Alert>
        <p className="muted">Hãy liên hệ quản trị viên của tổ chức để nhận liên kết mới.</p>
      </div>
    );
  }
  return <Form token={token} preview={preview.data} microsoft={microsoft} />;
}
