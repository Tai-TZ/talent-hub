import type { Metadata } from "next";
import { InviteForm } from "@/components/InviteForm";
import { QueryProvider } from "@/components/QueryProvider";
import { getOrgInfo } from "@/lib/server";

// Token nằm trong đường dẫn: không để lộ qua Referer và không cho công cụ tìm kiếm lập chỉ mục.
export const metadata: Metadata = { title: "Kích hoạt tài khoản", referrer: "no-referrer", robots: { index: false, follow: false } };

export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const [{ token }, org] = await Promise.all([params, getOrgInfo()]);
  return (
    <div className="auth">
      <section className="auth__hero" aria-labelledby="hero-title">
        <p className="auth__org">{org?.name ?? "Talent Hub"}</p>
        <h2 id="hero-title" className="auth__headline">
          Một tài khoản, đúng quyền cho đúng việc.
        </h2>
        <p className="auth__lead">Hoàn tất bước cuối để vào hệ thống. Mật khẩu chỉ bạn biết; quản trị viên không thể xem hay đặt thay.</p>
      </section>
      <main className="auth__panel" id="main">
        <QueryProvider>
          <InviteForm token={token} />
        </QueryProvider>
      </main>
    </div>
  );
}
