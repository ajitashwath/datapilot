"use client";

import Link from "next/link";
import Script from "next/script";
import { useEffect, useState } from "react";
import { site } from "@/lib/site";

type Choice = "all" | "essential";

export const CONSENT_KEY = "datapilot-consent";
export const CONSENT_EVENT = "datapilot:cookie-settings";

function readChoice(): Choice | null {
  try {
    const value = localStorage.getItem(CONSENT_KEY);
    return value === "all" || value === "essential" ? value : null;
  } catch {
    return null;
  }
}

function storeChoice(choice: Choice) {
  try {
    localStorage.setItem(CONSENT_KEY, choice);
  } catch {
    return;
  }
}

function clearAnalyticsCookies() {
  document.cookie.split(";").forEach((cookie) => {
    const name = cookie.split("=")[0].trim();
    if (!name.startsWith("_ga")) return;
    const expired = `${name}=; Max-Age=0; path=/`;
    document.cookie = expired;
    document.cookie = `${expired}; domain=${location.hostname}`;
    document.cookie = `${expired}; domain=.${location.hostname.replace(/^www\./, "")}`;
  });
}

export default function CookieConsent() {
  const [choice, setChoice] = useState<Choice | null>(null);
  const [open, setOpen] = useState(false);
  const analytics = Boolean(site.analyticsId);

  useEffect(() => {
    const stored = readChoice();
    setChoice(stored);
    setOpen(stored === null);
    const reopen = () => setOpen(true);
    window.addEventListener(CONSENT_EVENT, reopen);
    return () => window.removeEventListener(CONSENT_EVENT, reopen);
  }, []);

  function decide(next: Choice) {
    storeChoice(next);
    setChoice(next);
    setOpen(false);
    if (next === "essential" && analytics) {
      (window as unknown as Record<string, boolean>)[`ga-disable-${site.analyticsId}`] = true;
      clearAnalyticsCookies();
    }
  }

  return (
    <>
      {analytics && choice === "all" && (
        <>
          <Script src={`https://www.googletagmanager.com/gtag/js?id=${site.analyticsId}`} strategy="afterInteractive" />
          <Script id="ga-init" strategy="afterInteractive">
            {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}gtag("js",new Date());gtag("config","${site.analyticsId}");`}
          </Script>
        </>
      )}
      {open && (
        <section
          role="dialog"
          aria-modal="false"
          aria-labelledby="cookie-title"
          className="fixed inset-x-3 bottom-3 z-50 mx-auto max-w-xl rounded-2xl border border-slate-200 bg-surface p-4 shadow-float sm:inset-x-auto sm:right-4 sm:bottom-4"
        >
          <h2 id="cookie-title" className="text-sm font-semibold text-slate-900">
            {analytics ? "Cookies and analytics" : "Browser storage"}
          </h2>
          <p className="mt-1 text-sm leading-relaxed text-slate-600">
            {analytics
              ? "We use essential browser storage to keep you signed in and remember your theme. With your permission we also use Google Analytics cookies to understand which pages are useful. You can change this at any time."
              : "DataPilot uses only essential browser storage to keep you signed in and remember your theme and this choice. We do not use advertising or analytics cookies."}{" "}
            <Link href="/privacy#cookies" className="font-medium text-brand-700 underline">
              Privacy policy
            </Link>
          </p>
          <div className="mt-3 flex flex-wrap justify-end gap-2">
            {analytics ? (
              <>
                <button type="button" onClick={() => decide("essential")} className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-slate-300 hover:bg-slate-100">
                  Essential only
                </button>
                <button type="button" onClick={() => decide("all")} className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700">
                  Accept analytics
                </button>
              </>
            ) : (
              <button type="button" onClick={() => decide("essential")} className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700">
                Got it
              </button>
            )}
          </div>
        </section>
      )}
    </>
  );
}
