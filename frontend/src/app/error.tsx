"use client";

import { useI18n } from "@/components/providers";
import { Button } from "@/components/ui/Button";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const { t } = useI18n();
  return (
    <main className="centered" id="main">
      <h1 className="th-type-h3">{t.errors.crashed}</h1>
      <p className="page-head__subtitle">{t.common.genericError}</p>
      {error.digest ? <p className="mono">{error.digest}</p> : null}
      <Button onClick={reset}>{t.common.retry}</Button>
    </main>
  );
}
