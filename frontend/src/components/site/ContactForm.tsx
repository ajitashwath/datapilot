"use client";

import { useEffect, useRef, useState } from "react";
import FormField from "@/components/FormField";
import { ApiError, type ContactMessage, getConfig, sendContact } from "@/lib/api";
import { emailError, type Errors, firstError, nameError } from "@/lib/validation";

type Field = "name" | "email" | "message";
const ORDER: Field[] = ["name", "email", "message"];
const MIN_MESSAGE = 20;
const MAX_MESSAGE = 4000;

const topics: { value: ContactMessage["topic"]; label: string }[] = [
  { value: "general", label: "General question" },
  { value: "sales", label: "Sales and teams" },
  { value: "support", label: "Product support" },
  { value: "security", label: "Security report" },
  { value: "privacy", label: "Privacy request" },
];

function messageError(value: string): string | undefined {
  const text = value.trim();
  if (!text) return "Enter a message.";
  if (text.length < MIN_MESSAGE) return `Tell us a little more. ${MIN_MESSAGE - text.length} more characters needed.`;
  if (text.length > MAX_MESSAGE) return `Keep the message under ${MAX_MESSAGE} characters.`;
  return undefined;
}

const validators: Record<Field, (v: string) => string | undefined> = { name: nameError, email: emailError, message: messageError };

export default function ContactForm({ fallbackEmail }: { fallbackEmail: string }) {
  const [available, setAvailable] = useState<boolean | null>(null);
  const [values, setValues] = useState({ name: "", email: "", topic: "general" as ContactMessage["topic"], message: "", website: "" });
  const [errors, setErrors] = useState<Errors<Field>>({});
  const [touched, setTouched] = useState<Partial<Record<Field, boolean>>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const summaryRef = useRef<HTMLDivElement>(null);
  const sentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getConfig()
      .then((config) => setAvailable(Boolean(config.contact_form)))
      .catch(() => setAvailable(false));
  }, []);

  useEffect(() => {
    if (sent) sentRef.current?.focus();
  }, [sent]);

  function update(field: Field | "topic" | "website", value: string) {
    setValues((v) => ({ ...v, [field]: value }));
    if (field in validators && touched[field as Field]) {
      setErrors((e) => ({ ...e, [field]: validators[field as Field](value) }));
    }
  }

  function blur(field: Field) {
    setTouched((t) => ({ ...t, [field]: true }));
    setErrors((e) => ({ ...e, [field]: validators[field](values[field]) }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    const found: Errors<Field> = Object.fromEntries(ORDER.map((f) => [f, validators[f](values[f])]));
    setErrors(found);
    setTouched({ name: true, email: true, message: true });
    const first = firstError(ORDER, found);
    if (first) {
      document.getElementById(`contact-${first}`)?.focus();
      return;
    }
    setBusy(true);
    try {
      await sendContact({ ...values, name: values.name.trim(), email: values.email.trim(), message: values.message.trim() });
      setSent(true);
    } catch (failure) {
      if (failure instanceof ApiError && failure.code.startsWith("invalid_")) {
        const field = failure.code.slice("invalid_".length) as Field;
        if (ORDER.includes(field)) {
          setErrors((e) => ({ ...e, [field]: failure.message }));
          document.getElementById(`contact-${field}`)?.focus();
          return;
        }
      }
      setFormError(failure instanceof ApiError ? failure.message : "Your message could not be sent. Please try again.");
      requestAnimationFrame(() => summaryRef.current?.focus());
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <div ref={sentRef} tabIndex={-1} role="status" className="mt-4 rounded-xl bg-emerald-50 p-5 text-emerald-800 outline-none ring-1 ring-emerald-200">
        <p className="font-semibold">Thanks, your message is on its way.</p>
        <p className="mt-1 text-sm">We will reply to {values.email.trim()}.</p>
      </div>
    );
  }

  if (available === false) {
    return (
      <p className="mt-4 rounded-xl bg-slate-100 p-5 text-sm leading-relaxed text-slate-700">
        The contact form is not available right now.{" "}
        {fallbackEmail ? (
          <>
            Please email{" "}
            <a href={`mailto:${fallbackEmail}`} className="font-semibold text-brand-700 underline">
              {fallbackEmail}
            </a>{" "}
            instead.
          </>
        ) : (
          "Please try again later."
        )}
      </p>
    );
  }

  const remaining = MAX_MESSAGE - values.message.length;

  return (
    <form onSubmit={submit} noValidate className="mt-4 space-y-4" aria-busy={busy}>
      {formError && (
        <div ref={summaryRef} tabIndex={-1} role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 outline-none ring-1 ring-rose-200">
          {formError}
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="contact-name" label="Name" error={errors.name}>
          {(control) => <input {...control} value={values.name} onChange={(e) => update("name", e.target.value)} onBlur={() => blur("name")} autoComplete="name" maxLength={80} required />}
        </FormField>
        <FormField id="contact-email" label="Email" error={errors.email}>
          {(control) => (
            <input {...control} type="email" value={values.email} onChange={(e) => update("email", e.target.value)} onBlur={() => blur("email")} autoComplete="email" maxLength={254} required />
          )}
        </FormField>
      </div>
      <FormField id="contact-topic" label="Topic">
        {(control) => (
          <select {...control} value={values.topic} onChange={(e) => update("topic", e.target.value)}>
            {topics.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        )}
      </FormField>
      <FormField
        id="contact-message"
        label="Message"
        error={errors.message}
        hint={<span aria-live="polite">{remaining < 500 ? `${remaining} characters left` : `At least ${MIN_MESSAGE} characters. Please do not include passwords or API keys.`}</span>}
      >
        {(control) => (
          <textarea {...control} rows={6} value={values.message} onChange={(e) => update("message", e.target.value)} onBlur={() => blur("message")} maxLength={MAX_MESSAGE} required />
        )}
      </FormField>
      <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
        <label htmlFor="contact-website">Website</label>
        <input id="contact-website" tabIndex={-1} autoComplete="off" value={values.website} onChange={(e) => update("website", e.target.value)} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-slate-500">
          We use your details only to reply. See our{" "}
          <a href="/privacy" className="underline hover:text-brand-700">
            privacy policy
          </a>
          .
        </p>
        <button type="submit" disabled={busy || available === null} className="rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50">
          {busy ? "Sending..." : "Send message"}
        </button>
      </div>
    </form>
  );
}
