import { describe, expect, it } from "vitest";
import { emailError, firstError, nameError, newPasswordError, passwordStrength } from "./validation";
import { describeDays, parseHours, telHref } from "./site";

describe("emailError", () => {
  it("accepts ordinary addresses", () => {
    expect(emailError("ann@example.com")).toBeUndefined();
    expect(emailError("  ann.lee+data@sub.example.co.uk ")).toBeUndefined();
  });

  it("explains what is wrong", () => {
    expect(emailError("")).toBe("Enter your email address.");
    expect(emailError("ann@")).toMatch(/name@example.com/);
    expect(emailError("ann example@x.com")).toMatch(/name@example.com/);
    expect(emailError("ann@example")).toMatch(/name@example.com/);
  });
});

describe("nameError", () => {
  it("requires a non blank name of at most 80 characters", () => {
    expect(nameError("   ")).toBe("Enter your name.");
    expect(nameError("a".repeat(81))).toMatch(/80/);
    expect(nameError("Ann")).toBeUndefined();
  });
});

describe("newPasswordError", () => {
  it("matches the server rule of 10 to 200 characters", () => {
    expect(newPasswordError("")).toBe("Choose a password.");
    expect(newPasswordError("short")).toMatch(/5 more to go/);
    expect(newPasswordError("a".repeat(201))).toMatch(/200/);
    expect(newPasswordError("correct horse")).toBeUndefined();
  });
});

describe("passwordStrength", () => {
  it("grades length, variety and repetition", () => {
    expect(passwordStrength("abc").score).toBe(0);
    expect(passwordStrength("aaaaaaaaaaaa").score).toBe(1);
    expect(passwordStrength("abcdefghij").score).toBe(2);
    expect(passwordStrength("correct horse battery").score).toBe(3);
    expect(passwordStrength("Tr0ub4dor&3x").score).toBe(3);
  });
});

describe("firstError", () => {
  it("returns the first invalid field in form order", () => {
    expect(firstError(["name", "email", "message"], { message: "x", email: "y" })).toBe("email");
    expect(firstError(["name"], {})).toBeUndefined();
  });
});

describe("parseHours", () => {
  it("parses schema.org style ranges", () => {
    expect(parseHours("Mo-Fr 09:00-18:00, Sa 10:00-14:00")).toEqual([
      { days: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], opens: "09:00", closes: "18:00" },
      { days: ["Saturday"], opens: "10:00", closes: "14:00" },
    ]);
  });

  it("rejects anything malformed instead of showing wrong hours", () => {
    expect(parseHours("")).toEqual([]);
    expect(parseHours("Fr-Mo 09:00-18:00")).toEqual([]);
    expect(parseHours("Mo 18:00-09:00")).toEqual([]);
    expect(parseHours("Mo-Fr 9am-6pm")).toEqual([]);
    expect(parseHours("Mo-Fr 09:00-18:00, nonsense")).toEqual([]);
  });

  it("describes day ranges", () => {
    expect(describeDays(["Monday", "Tuesday", "Wednesday"])).toBe("Monday to Wednesday");
    expect(describeDays(["Sunday"])).toBe("Sunday");
  });
});

describe("telHref", () => {
  it("keeps only digits and the leading plus", () => {
    expect(telHref("+91 98765 43210")).toBe("tel:+919876543210");
    expect(telHref("(555) 010-0199")).toBe("tel:5550100199");
  });
});
