"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import LinkPage from "@/components/LinkPage";
import { ApiError, setToken, ssoCallback } from "@/lib/api";

function Callback() {
  const params = useSearchParams();
  const [message, setMessage] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const code = params.get("code");
    const state = params.get("state");
    if (!code || !state) {
      setMessage(params.get("error_description") ?? "The sign-in did not complete.");
      return;
    }
    ssoCallback(code, state)
      .then((result) => {
        setToken(result.token as string);
        window.location.replace("/");
      })
      .catch((failure) => setMessage(failure instanceof ApiError ? failure.message : "The sign-in could not be completed."));
  }, [params]);

  return (
    <LinkPage title="Single sign-on">
      {message ? (
        <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {message} <a href="/" className="font-medium underline">Back to sign in</a>
        </p>
      ) : (
        <p role="status" className="text-sm text-slate-600">Signing you in...</p>
      )}
    </LinkPage>
  );
}

export default function SsoPage() {
  return (
    <Suspense fallback={null}>
      <Callback />
    </Suspense>
  );
}
