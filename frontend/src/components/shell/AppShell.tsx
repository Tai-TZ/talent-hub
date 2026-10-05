"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { isActive, NAV_GROUPS, visibleNav } from "@/lib/nav";
import { useI18n, useMe } from "../providers";
import { LanguageSwitch } from "../LanguageSwitch";
import { BarsIcon, CloseIcon } from "../icons";
import { Assistant } from "@/features/assistant/Assistant";
import { UserMenu } from "./UserMenu";

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useI18n();
  const me = useMe();
  const pathname = usePathname();
  const items = visibleNav(me.permissions);
  const groups = (Object.keys(NAV_GROUPS) as (keyof typeof NAV_GROUPS)[])
    .map((key) => ({ key, title: NAV_GROUPS[key]?.(t) ?? null, items: items.filter((i) => i.group === key) }))
    .filter((g) => g.items.length > 0);
  return (
    <nav aria-label={t.nav.primary}>
      {groups.map((group) => (
        <div key={group.key} role="group" aria-labelledby={group.title ? `nav-group-${group.key}` : undefined}>
          {group.title ? (
            <p className="nav-group" id={`nav-group-${group.key}`}>
              {group.title}
            </p>
          ) : null}
          <ul className="nav-list">
            {group.items.map((item) => (
              <li key={item.href}>
                <Link href={item.href} className="nav-link" aria-current={isActive(item, pathname) ? "page" : undefined} onClick={onNavigate}>
                  {item.label(t)}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function AppShell({ orgName, children }: { orgName: string; children: ReactNode }) {
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const drawer = useRef<HTMLDialogElement>(null);
  const [signingOut, setSigningOut] = useState(false);

  // Đóng menu di động khi chuyển trang.
  useEffect(() => {
    drawer.current?.close();
  }, [pathname]);

  async function logout() {
    setSigningOut(true);
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      router.replace("/login");
      router.refresh();
    }
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        {t.app.skipToContent}
      </a>
      <header className="shell__header">
        <button type="button" className="icon-btn shell__menu-btn" aria-label={t.nav.menu} onClick={() => drawer.current?.showModal()}>
          <BarsIcon size={20} />
        </button>
        <Link href="/dashboard" className="brand">
          <span className="brand__mark">{orgName}</span>
          <span className="brand__divider" aria-hidden="true" />
          <span className="brand__product">{t.app.name}</span>
        </Link>
        <div className="shell__actions">
          <LanguageSwitch />
          <UserMenu onLogout={logout} signingOut={signingOut} />
        </div>
      </header>

      <div className="shell__body">
        <aside className="shell__side">
          <NavLinks />
        </aside>
        <main id="main" className="shell__main" tabIndex={-1}>
          {children}
        </main>
      </div>

      <Assistant />

      {/* <dialog> modal: trình duyệt lo focus trap, Escape và inert nền. */}
      <dialog ref={drawer} className="nav-drawer" aria-label={t.nav.primary} onClick={(e) => e.target === drawer.current && drawer.current?.close()}>
        <div className="nav-drawer__head">
          <span className="brand__mark">{orgName}</span>
          <button type="button" className="icon-btn" aria-label={t.common.close} onClick={() => drawer.current?.close()}>
            <CloseIcon size={22} />
          </button>
        </div>
        <NavLinks onNavigate={() => drawer.current?.close()} />
      </dialog>
    </div>
  );
}
