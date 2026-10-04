import { redirect } from "next/navigation";
import { AppShell } from "@/components/shell/AppShell";
import { SessionProvider } from "@/components/providers";
import { QueryProvider } from "@/components/QueryProvider";
import { getOrgInfo, getPathname, getSession } from "@/lib/server";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const [session, pathname] = await Promise.all([getSession(), getPathname()]);
  if (session.status !== "ok") redirect(`/session/refresh?next=${encodeURIComponent(pathname)}`);

  const { me } = session;
  // Người dùng mới phải đổi mật khẩu trước khi vào bất kỳ chức năng nào khác.
  if (me.must_change_password && !pathname.startsWith("/account/password")) redirect("/account/password?first=1");

  const org = await getOrgInfo();
  return (
    <SessionProvider me={me}>
      <QueryProvider>
        <AppShell orgName={org?.name ?? me.organization}>{children}</AppShell>
      </QueryProvider>
    </SessionProvider>
  );
}
