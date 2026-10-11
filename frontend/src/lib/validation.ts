const EMAIL_PATTERN = /^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$/;

export const MIN_PASSWORD = 10;
export const MAX_PASSWORD = 200;

export type Errors<K extends string> = Partial<Record<K, string>>;

export function emailError(value: string): string | undefined {
  const email = value.trim();
  if (!email) return "Enter your email address.";
  if (email.length > 254 || !EMAIL_PATTERN.test(email)) return "Enter an email address in the format name@example.com.";
  return undefined;
}

export function nameError(value: string): string | undefined {
  const name = value.trim();
  if (!name) return "Enter your name.";
  if (name.length > 80) return "Use 80 characters or fewer.";
  return undefined;
}

export function newPasswordError(value: string): string | undefined {
  if (!value) return "Choose a password.";
  if (value.length < MIN_PASSWORD) return `Use at least ${MIN_PASSWORD} characters. ${MIN_PASSWORD - value.length} more to go.`;
  if (value.length > MAX_PASSWORD) return `Use ${MAX_PASSWORD} characters or fewer.`;
  return undefined;
}

export function passwordStrength(value: string): { score: 0 | 1 | 2 | 3; label: string } {
  if (value.length < MIN_PASSWORD) return { score: 0, label: "Too short" };
  const variety = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(value)).length;
  const unique = new Set(value).size;
  if (unique < 5) return { score: 1, label: "Weak: too many repeated characters" };
  if (value.length >= 16 || (value.length >= 12 && variety >= 3)) return { score: 3, label: "Strong" };
  return { score: 2, label: "Good: longer is stronger" };
}

export function firstError<K extends string>(order: K[], errors: Errors<K>): K | undefined {
  return order.find((key) => errors[key]);
}
