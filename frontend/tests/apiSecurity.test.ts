import assert from "node:assert/strict";
import test from "node:test";

class MemoryStorage {
  values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }
}

const sessionStorage = new MemoryStorage();
const localStorage = new MemoryStorage();
Object.defineProperty(globalThis, "window", {
  configurable: true,
  value: { sessionStorage, localStorage },
});

const apiModule = await import("../src/api.ts");
const {
  SERVICE_TOKEN_SESSION_KEY,
  authorizedFetch,
  clearServiceAccessToken,
  getServiceAccessToken,
  setServiceAccessToken,
} = apiModule;

test("service token is sent only in Authorization and stored only for the tab session", async () => {
  const token = "browser-session-token";
  let request: Request | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    request = new Request(input, init);
    return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
  };

  try {
    setServiceAccessToken(token);
    await authorizedFetch("http://example.test/api/v2/documents?scope=visible");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(getServiceAccessToken(), token);
  assert.equal(sessionStorage.getItem(SERVICE_TOKEN_SESSION_KEY), token);
  assert.equal(localStorage.getItem(SERVICE_TOKEN_SESSION_KEY), null);
  assert.equal(request?.headers.get("Authorization"), `Bearer ${token}`);
  assert.equal(request?.url.includes(token), false);

  clearServiceAccessToken();
  assert.equal(getServiceAccessToken(), "");
  assert.equal(sessionStorage.getItem(SERVICE_TOKEN_SESSION_KEY), null);
});
