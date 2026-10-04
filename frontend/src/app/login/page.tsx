import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { LoginForm } from "@/components/LoginForm";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { safeNextPath } from "@/lib/org";
import { getOrgInfo, getSession, getT } from "@/lib/server";

export const metadata: Metadata = { title: "Đăng nhập" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  const target = safeNextPath(next);

  const session = await getSession();
  if (session.status === "ok") redirect(target);

  const [org, { t }] = await Promise.all([getOrgInfo(), getT()]);

  return (
    <div className="auth">
      <section className="auth__hero" aria-labelledby="hero-title">
        <p className="auth__org">{org?.name ?? t.app.name}</p>
        <h1 id="hero-title" className="auth__headline">
          {t.login.heroTitle}
        </h1>
        <p className="auth__lead">{t.login.heroBody}</p>
      </section>
      <main className="auth__panel" id="main">
        <div className="auth__lang">
          <LanguageSwitch />
        </div>
        <LoginForm next={target} />
      </main>
    </div>
  );
}
