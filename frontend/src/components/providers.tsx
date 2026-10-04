"use client";

import { createContext, useContext, type ReactNode } from "react";
import { format, getMessages, type Locale, type Messages } from "@/lib/i18n";
import type { Me } from "@/lib/types";

interface I18nValue {
  locale: Locale;
  t: Messages;
  fmt: (template: string, values: Record<string, string>) => string;
}

const I18nContext = createContext<I18nValue | null>(null);
const SessionContext = createContext<Me | null>(null);

export function I18nProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  const value: I18nValue = { locale, t: getMessages(locale), fmt: format };
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n phải nằm trong I18nProvider");
  return ctx;
}

export function SessionProvider({ me, children }: { me: Me; children: ReactNode }) {
  return <SessionContext.Provider value={me}>{children}</SessionContext.Provider>;
}

export function useMe(): Me {
  const me = useContext(SessionContext);
  if (!me) throw new Error("useMe phải nằm trong SessionProvider");
  return me;
}
