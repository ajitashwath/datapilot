"use client";

import { CONSENT_EVENT } from "./CookieConsent";

export default function CookieSettingsButton({ className }: { className?: string }) {
  return (
    <button type="button" onClick={() => window.dispatchEvent(new Event(CONSENT_EVENT))} className={className}>
      Cookie settings
    </button>
  );
}
