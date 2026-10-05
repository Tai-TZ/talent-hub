"use client";

import { useRouter } from "next/navigation";
import { useTransition, type ReactNode } from "react";
import { setLocale } from "@/app/actions";
import type { Locale } from "@/lib/i18n";
import { FlagUS, FlagVN } from "./icons";
import { useI18n } from "./providers";

const DISPLAY: Record<Locale, { code: string; flag: () => ReactNode; next: Locale }> = {
  vi: { code: "VIE", flag: () => <FlagVN />, next: "en" },
  en: { code: "ENG", flag: () => <FlagUS />, next: "vi" },
};

/** Một nút: hiện ngôn ngữ đang dùng (cờ + mã), bấm để đổi sang ngôn ngữ còn lại. Lựa chọn lưu trong cookie phía server
 * nên server component cũng đổi theo. */
export function LanguageSwitch() {
  const { locale, t } = useI18n();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const current = DISPLAY[locale];

  function toggle() {
    startTransition(async () => {
      await setLocale(current.next);
      router.refresh();
    });
  }

  return (
    <button type="button" className="lang-toggle" onClick={toggle} disabled={pending} aria-label={t.common.switchLanguage} title={t.common.switchLanguage}>
      {current.flag()}
      <span className="lang-toggle__code">{current.code}</span>
    </button>
  );
}
