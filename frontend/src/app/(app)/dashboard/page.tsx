import type { Metadata } from "next";
import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { format } from "@/lib/i18n";
import { visibleNav } from "@/lib/nav";
import { getOrgInfo, getSession, getT } from "@/lib/server";

export const metadata: Metadata = { title: "Tổng quan" };

export default async function DashboardPage() {
  const [session, org, { t }] = await Promise.all([getSession(), getOrgInfo(), getT()]);
  if (session.status !== "ok") return null; // layout đã chuyển hướng
  const { me } = session;
  const links = visibleNav(me.permissions).filter((item) => item.href !== "/dashboard");
  const descriptions: Record<string, string> = {
    "/admin/audit-logs": t.dashboard.auditDesc,
    "/account/password": t.dashboard.passwordDesc,
  };

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

      <section aria-labelledby="links-title" className="stack">
        <h2 id="links-title" className="th-type-h4">
          {t.dashboard.quickLinks}
        </h2>
        {links.length === 0 ? (
          <p className="page-head__subtitle">{t.dashboard.noLinks}</p>
        ) : (
          <div className="card-grid">
            {links.map((item) => (
              <Link key={item.href} href={item.href} className="th-card th-card--interactive link-card">
                <span className="link-card__title">{item.label(t)}</span>
                <span className="link-card__desc">{descriptions[item.href]}</span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
