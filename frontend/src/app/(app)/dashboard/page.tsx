import type { Metadata } from "next";
import { Badge } from "@/components/ui/Badge";
import { DashboardTasks } from "@/features/dashboard/Tasks";
import { Notifications } from "@/features/dashboard/Notifications";
import { format } from "@/lib/i18n";
import { getOrgInfo, getSession, getT } from "@/lib/server";

export const metadata: Metadata = { title: "Tổng quan" };

export default async function DashboardPage() {
  const [session, org, { t }] = await Promise.all([getSession(), getOrgInfo(), getT()]);
  if (session.status !== "ok") return null; // layout đã chuyển hướng
  const { me } = session;

  return (
    <div className="stack">
      <header className="page-head">
        <h1 className="page-head__title">{format(t.dashboard.greeting, { name: me.full_name })}</h1>
        <p className="page-head__subtitle">{format(t.dashboard.subtitle, { org: org?.name ?? me.organization })}</p>
      </header>

      <section aria-labelledby="roles-title" className="stack">
        <h2 id="roles-title" className="th-type-h4">
          {t.dashboard.roles}
        </h2>
        <div className="badge-row">
          {me.roles.map((role) => (
            <Badge key={role}>{t.roles[role] ?? role}</Badge>
          ))}
        </div>
      </section>

      <DashboardTasks />
      <Notifications />
    </div>
  );
}
