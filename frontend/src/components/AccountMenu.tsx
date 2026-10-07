"use client";

import { useEffect, useRef, useState } from "react";
import type { User } from "@/lib/types";

interface AccountMenuProps {
  user: User | null;
  twoFactor: boolean;
  onSettings: () => void;
  onPassword: () => void;
  onTwoFactor: () => void;
  onSignOut: () => void;
}

const itemClass = "block w-full rounded-lg px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100";

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

export default function AccountMenu({ user, twoFactor, onSettings, onPassword, onTwoFactor, onSignOut }: AccountMenuProps) {
  const [open, setOpen] = useState(false);
  const [dark, setDark] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
    function close(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function toggleTheme() {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("datapilot-theme", next ? "dark" : "light");
    } catch {}
    setDark(next);
  }

  function pick(action: () => void) {
    setOpen(false);
    action();
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={user ? `Account menu for ${user.name}` : "Menu"}
        className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left hover:bg-slate-100"
      >
        <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white">
          {user ? initials(user.name) : "DP"}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-slate-900">{user ? user.name : "Menu"}</span>
          <span className="block truncate text-xs text-slate-500">{user ? user.email : "Settings and theme"}</span>
        </span>
        <span aria-hidden="true" className="text-slate-400">
          &#8943;
        </span>
      </button>
      {open && (
        <div role="menu" className="absolute bottom-full left-0 z-30 mb-2 w-full min-w-[15rem] rounded-xl border border-slate-200 bg-surface p-1.5 shadow-float">
          <button role="menuitem" onClick={() => pick(onSettings)} className={itemClass}>
            Settings and API key
          </button>
          {user && (
            <button role="menuitem" onClick={() => pick(onPassword)} className={itemClass}>
              Change password
            </button>
          )}
          {user && twoFactor && (
            <button role="menuitem" onClick={() => pick(onTwoFactor)} className={itemClass}>
              Two-factor sign-in
            </button>
          )}
          <button role="menuitem" onClick={toggleTheme} className={itemClass}>
            {dark ? "Switch to light theme" : "Switch to dark theme"}
          </button>
          {user && (
            <button role="menuitem" onClick={() => pick(onSignOut)} className={`${itemClass} text-rose-700`}>
              Sign out
            </button>
          )}
        </div>
      )}
    </div>
  );
}
