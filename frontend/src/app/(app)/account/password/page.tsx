import type { Metadata } from "next";
import { PasswordForm } from "@/components/PasswordForm";
import { getT } from "@/lib/server";

export const metadata: Metadata = { title: "Đổi mật khẩu" };

export default async function PasswordPage({ searchParams }: { searchParams: Promise<{ first?: string }> }) {
  const [{ first }, { t }] = await Promise.all([searchParams, getT()]);
  return (
    <div className="stack">
      <header className="page-head">
        <h1 className="page-head__title">{t.password.title}</h1>
      </header>
      <PasswordForm firstTime={first === "1"} />
    </div>
  );
}
