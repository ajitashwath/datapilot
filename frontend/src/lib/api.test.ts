import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, getConfig, getToken, listTeams, setToken, waitForJob } from "./api";

function memoryStorage() {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
  };
}

const reply = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

beforeEach(() => {
  vi.stubGlobal("sessionStorage", memoryStorage());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("auth token handling", () => {
  it("stores the token and sends it as a bearer header", async () => {
    const fetchMock = vi.fn(() => reply(200, []));
    vi.stubGlobal("fetch", fetchMock);
    setToken("abc123");
    expect(getToken()).toBe("abc123");
    await listTeams();
    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer abc123");
  });

  it("sends no Authorization header when signed out", async () => {
    const fetchMock = vi.fn(() => reply(200, { auth_mode: "none" }));
    vi.stubGlobal("fetch", fetchMock);
    setToken(null);
    await getConfig();
    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init?.headers).toBeUndefined();
    expect(getToken()).toBeNull();
  });

  it("surfaces the server error code and message", async () => {
    vi.stubGlobal("fetch", vi.fn(() => reply(401, { error: { code: "unauthorized", message: "Please sign in to continue." } })));
    const failure = await listTeams().catch((e) => e);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure.code).toBe("unauthorized");
    expect(failure.status).toBe(401);
    expect(failure.message).toBe("Please sign in to continue.");
  });

  it("reports an unreachable server in plain language", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("network down"))));
    const failure = await listTeams().catch((e) => e);
    expect(failure.code).toBe("network");
    expect(failure.message).toContain("Cannot reach");
  });
});

describe("waitForJob", () => {
  it("polls until the job finishes and reports each update", async () => {
    vi.useFakeTimers();
    const states = ["queued", "running", "done"];
    vi.stubGlobal("fetch", vi.fn(() => reply(200, { id: "j1", kind: "url", status: states.shift(), message: "ok", datasets: ["sales"] })));
    const seen: string[] = [];
    const pending = waitForJob("j1", (job) => seen.push(job.status));
    await vi.advanceTimersByTimeAsync(2000);
    const finished = await pending;
    expect(seen).toEqual(["queued", "running", "done"]);
    expect(finished.datasets).toEqual(["sales"]);
  });

  it("returns error jobs without throwing", async () => {
    vi.stubGlobal("fetch", vi.fn(() => reply(200, { id: "j2", kind: "url", status: "error", message: "Link is not CSV", datasets: [] })));
    const job = await waitForJob("j2");
    expect(job.status).toBe("error");
    expect(job.message).toBe("Link is not CSV");
  });
});
