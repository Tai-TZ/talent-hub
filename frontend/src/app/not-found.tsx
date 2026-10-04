import { ButtonLink } from "@/components/ui/Button";
import { getT } from "@/lib/server";

export default async function NotFound() {
  const { t } = await getT();
  return (
    <main className="centered" id="main">
      <h1 className="th-type-h3">404</h1>
      <p className="page-head__subtitle">{t.errors.notFound}</p>
      <ButtonLink href="/dashboard">{t.errors.notFoundAction}</ButtonLink>
    </main>
  );
}
