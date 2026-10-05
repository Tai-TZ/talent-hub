"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { initials } from "@/lib/format";
import { ChevronDownIcon, KeyIcon, SignOutIcon } from "../icons";
import { useI18n, useMe } from "../providers";


/** Menu tài khoản theo mẫu "menu button" của WAI-ARIA: mũi tên lên/xuống, Home/End, Escape trả focus về nút. */
export function UserMenu({ onLogout, signingOut }: { onLogout: () => void; signingOut: boolean }) {
  const { t } = useI18n();
  const me = useMe();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  const items = () => Array.from(root.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);

  function openMenu(focus: "first" | "last" = "first") {
    setOpen(true);
    requestAnimationFrame(() => {
      const list = items();
      (focus === "first" ? list[0] : list.at(-1))?.focus();
    });
  }

  function close(returnFocus = true) {
    setOpen(false);
    if (returnFocus) button.current?.focus();
  }

  // Bấm ra ngoài thì đóng (không kéo focus về nút để không cướp focus của nơi vừa bấm).
  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  function onMenuKey(e: KeyboardEvent<HTMLDivElement>) {
    const list = items();
    const index = list.indexOf(document.activeElement as HTMLElement);
    const move = (i: number) => list[(i + list.length) % list.length]?.focus();
    if (e.key === "ArrowDown") move(index + 1);
    else if (e.key === "ArrowUp") move(index - 1);
    else if (e.key === "Home") move(0);
    else if (e.key === "End") move(list.length - 1);
    else if (e.key === "Escape") close();
    else if (e.key === "Tab") return setOpen(false);
    else return;
    e.preventDefault();
  }

  return (
    <div className="user-menu" ref={root}>
      <button
        ref={button}
        type="button"
        className="user-menu__trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={`${t.nav.account}: ${me.full_name}`}
        onClick={() => (open ? close(false) : openMenu())}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            openMenu("first");
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            openMenu("last");
          }
        }}
      >
        <span className="th-avatar th-avatar--sm" aria-hidden="true">
          {initials(me.full_name)}
        </span>
        <span className="user-menu__name">{me.full_name}</span>
        <ChevronDownIcon size={16} className="user-menu__chevron" />
      </button>

      {open ? (
        <div className="user-menu__panel" onKeyDown={onMenuKey}>
          <div className="user-menu__who">
            <span className="th-avatar" aria-hidden="true">
              {initials(me.full_name)}
            </span>
            <span className="user-menu__who-text">
              <strong>{me.full_name}</strong>
              <span className="muted">{me.email}</span>
            </span>
          </div>
          <div role="menu" id={menuId} aria-label={t.nav.account} className="user-menu__items">
            <Link role="menuitem" href="/account/password" className="user-menu__item" onClick={() => setOpen(false)}>
              <KeyIcon size={16} />
              {t.nav.password}
            </Link>
            <button role="menuitem" type="button" className="user-menu__item user-menu__item--danger" disabled={signingOut} onClick={onLogout}>
              <SignOutIcon size={16} />
              {t.nav.logout}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
