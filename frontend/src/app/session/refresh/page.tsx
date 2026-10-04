"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { useI18n } from "@/components/providers";
import { refreshSession } from "@/lib/api";
import { safeNextPath } from "@/lib/org";

/** Access token hết hạn là chuyện bình thường: thử làm mới bằng refresh token trước khi bắt đăng nhập lại. */
function Restore() {
  const { t } = useI18n();
  const router = useRouter();
  const next = safeNextPath(useSearchParams().get("next"));

  useEffect(() => {
    let cancelled = false;
    void refreshSession().then((ok) => {
      if (cancelled) return;
      router.replace(ok ? next : `/login?next=${encodeURIComponent(next)}`);
      router.refresh();
    });
    return () => {
      cancelled = true;
    };
  }, [next, router]);

  return (
    <main className="centered" id="main">
      <p role="status">{t.session.restoring}</p>
    </main>
  );
}

export default function SessionRefreshPage() {
  return (
    <Suspense>
      <Restore />
    </Suspense>
  );
}
