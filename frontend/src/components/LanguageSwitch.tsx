"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { setLocale } from "@/app/actions";
import { LOCALES, type Locale } from "@/lib/i18n";
import { useI18n } from "./providers";

/** Chuyển ngôn ngữ giao diện; lựa chọn lưu trong cookie phía server nên server component cũng đổi theo. */
export function LanguageSwitch() {
  const { locale, t } = useI18n();
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  function change(next: Locale) {
    startTransition(async () => {
      await setLocale(next);
      router.refresh();
    });
  }

  return (
    <div className="lang-switch" role="group" aria-label={t.common.language}>
      {LOCALES.map((code) => (
        <button
          key={code}
          type="button"
          className="lang-switch__btn"
          aria-pressed={locale === code}
          disabled={pending}
          onClick={() => change(code)}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
