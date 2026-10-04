import type { Metadata } from "next";
import { AuditTable } from "@/components/AuditTable";
import { Alert } from "@/components/ui/Alert";
import { getSession, getT } from "@/lib/server";

export const metadata: Metadata = { title: "Nhật ký hoạt động" };

export default async function AuditLogsPage() {
  const [session, { t }] = await Promise.all([getSession(), getT()]);
  if (session.status !== "ok") return null;
  const allowed = session.me.permissions.includes("audit.read");

  return (
    <div className="stack">
      <header className="page-head">
        <h1 className="page-head__title">{t.audit.title}</h1>
        <p className="page-head__subtitle">{t.audit.subtitle}</p>
      </header>
      {allowed ? <AuditTable /> : <Alert tone="warning">{t.audit.forbidden}</Alert>}
    </div>
  );
}
