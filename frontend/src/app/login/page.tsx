"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import AuthGate, { type AuthMode } from "@/components/AuthGate";
import { ApiError, getConfig, getToken, setToken } from "@/lib/api";
import type { AppConfig } from "@/lib/types";

const MODES: AuthMode[] = ["login", "register", "forgot"];

function Login() {
  const router = useRouter();
  const params = useSearchParams();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requested = params.get("mode") as AuthMode | null;
  const initialMode = requested && MODES.includes(requested) ? requested : "login";
  const message = params.get("expired") ? "Your session ended. Please sign in again." : null;

  useEffect(() => {
    if (getToken()) {
      router.replace("/app");
      return;
    }
    getConfig()
      .then((cfg) => {
        if (!cfg.auth_required) router.replace("/app");
        else setConfig(cfg);
      })
      .catch((failure) => setError(failure instanceof ApiError ? failure.message : "Cannot reach the DataPilot server."));
  }, [router]);

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <p role="alert" className="max-w-sm rounded-xl bg-rose-50 p-4 text-sm text-rose-700 ring-1 ring-rose-200">
          {error} Please try again in a moment.
        </p>
      </main>
    );
  }

  if (!config) {
    return (
      <main className="flex min-h-screen items-center justify-center" aria-busy="true">
        <span role="status" className="text-sm text-slate-500">
          Loading...
        </span>
      </main>
    );
  }

  return (
    <AuthGate
      config={config}
      message={message}
      initialMode={initialMode}
      onSharedToken={(token) => {
        setToken(token);
        router.replace("/app");
      }}
      onSignedIn={() => router.replace("/app")}
    />
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <Login />
    </Suspense>
  );
}
