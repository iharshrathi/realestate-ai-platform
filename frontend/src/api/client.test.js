import { beforeEach, describe, expect, it, vi } from "vitest";

// A minimal browser environment for the fetch wrapper (tests run in node).
const store = {};
globalThis.localStorage = {
  getItem: (k) => store[k] ?? null,
  setItem: (k, v) => (store[k] = v),
  removeItem: (k) => delete store[k],
};
globalThis.window = { location: { origin: "http://localhost" } };

const { api, ApiError, errorMessage, setUnauthorizedHandler, tokenStore } = await import("./client");

function mockFetch(status, body) {
  globalThis.fetch = vi.fn().mockResolvedValue({ status, ok: status < 400, json: async () => body });
}

describe("errorMessage", () => {
  it("handles string and validation-list details", () => {
    expect(errorMessage({ detail: "Nope" }, "x")).toBe("Nope");
    expect(errorMessage({ detail: [{ loc: ["body", "email"], msg: "invalid" }] }, "x")).toBe("email: invalid");
    expect(errorMessage(null, "fallback")).toBe("fallback");
  });
});

describe("request wrapper", () => {
  beforeEach(() => tokenStore.clear());

  it("sends the bearer token and query params, skipping empty ones", async () => {
    tokenStore.set("abc");
    mockFetch(200, { items: [] });
    await api.leads({ q: "ro", status: "", page: 2 });
    const [url, options] = fetch.mock.calls[0];
    expect(url.toString()).toBe("http://localhost/api/v1/leads?q=ro&page=2");
    expect(options.headers.Authorization).toBe("Bearer abc");
  });

  it("logs in with a form body and no auth header", async () => {
    tokenStore.set("old");
    mockFetch(200, { access_token: "t" });
    await api.login("a@b.co", "pw");
    const [, options] = fetch.mock.calls[0];
    expect(options.headers.Authorization).toBeUndefined();
    expect(options.body.toString()).toBe("username=a%40b.co&password=pw");
  });

  it("raises ApiError with the server message and triggers the 401 handler", async () => {
    tokenStore.set("expired");
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch(401, { detail: "Could not validate credentials" });
    await expect(api.me()).rejects.toMatchObject({ status: 401, message: "Could not validate credentials" });
    expect(handler).toHaveBeenCalledOnce();
  });

  it("reports an unreachable server clearly", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError("failed"));
    await expect(api.me()).rejects.toBeInstanceOf(ApiError);
    await expect(api.me()).rejects.toMatchObject({ status: 0 });
  });

  it("returns null for 204 responses", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ status: 204, ok: true });
    expect(await api.deleteLead(1)).toBeNull();
  });
});
