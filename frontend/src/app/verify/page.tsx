"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import LinkPage from "@/components/LinkPage";
import { ApiError, verifyEmail } from "@/lib/api";

function Verify() {
  const token = useSearchParams().get("token") ?? "";
  const [state, setState] = useState<"working" | "done" | "failed">("working");
  const [message, setMessage] = useState("");
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (!token) {
      setState("failed");
      setMessage("This link is missing its token.");
      return;
    }
    verifyEmail(token)
      .then(() => setState("done"))
      .catch((failure) => {
        setState("failed");
        setMessage(failure instanceof ApiError ? failure.message : "The link could not be verified.");
      });
  }, [token]);

  return (
    <LinkPage title="Confirm your email">
      {state === "working" && <p role="status" className="text-sm text-slate-600">Confirming your email...</p>}
      {state === "done" && (
        <p role="status" className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          Your email is confirmed. You can <a href="/" className="font-medium underline">sign in now</a>.
        </p>
      )}
      {state === "failed" && (
        <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {message} <a href="/" className="font-medium underline">Back to sign in</a> to request a new link.
        </p>
      )}
    </LinkPage>
  );
}

export default function VerifyPage() {
  return (
    <Suspense fallback={null}>
      <Verify />
    </Suspense>
  );
}
