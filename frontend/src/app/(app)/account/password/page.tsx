import type { Metadata } from "next";
import { PasswordForm } from "@/components/PasswordForm";
import { Alert } from "@/components/ui/Alert";
import { MicrosoftMark } from "@/components/icons";
import { getOrgInfo, getT } from "@/lib/server";

export const metadata: Metadata = { title: "Đổi mật khẩu" };

export default async function PasswordPage({ searchParams }: { searchParams: Promise<{ first?: string; linked?: string }> }) {
  const [{ first, linked }, { t }, org] = await Promise.all([searchParams, getT(), getOrgInfo()]);
  const microsoft = Boolean(org?.login_providers.includes("microsoft"));
  return (
    <div className="stack">
      <header className="page-head">
        <h1 className="page-head__title">{t.password.title}</h1>
      </header>
      <PasswordForm firstTime={first === "1"} />
      {microsoft ? (
        <section className="th-card form-card stack" aria-labelledby="ms-title">
          <h2 id="ms-title" className="th-type-h4">
            Đăng nhập bằng Microsoft
          </h2>
          <p className="muted">Liên kết tài khoản Microsoft của bạn để lần sau đăng nhập nhanh, không cần nhập mật khẩu. Chỉ liên kết khi chính bạn đang đăng nhập.</p>
          {linked === "1" ? <Alert tone="success">Đã liên kết tài khoản Microsoft.</Alert> : null}
          {/* Đường dẫn API cần điều hướng toàn trang tới Microsoft, không phải trang Next.js. */}
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
          <a className="th-button th-button--secondary" href="/api/v1/auth/microsoft/start?mode=link">
            <MicrosoftMark />
            Liên kết tài khoản Microsoft
          </a>
        </section>
      ) : null}
    </div>
  );
}
