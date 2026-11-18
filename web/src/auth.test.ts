// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthError, createDemoAuth, createServerAuth, logInProblem, signUpProblem } from "./auth";
import type { KeyValueStore } from "./auth";

function memoryStore(): KeyValueStore & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("form checks", () => {
  it("asks for a name, a real-looking email and a long enough password", () => {
    expect(signUpProblem({ name: " ", email: "a@b.co", password: "longenough" })?.field).toBe("name");
    expect(signUpProblem({ name: "Ana", email: "not-an-email", password: "longenough" })?.field).toBe("email");
    expect(signUpProblem({ name: "Ana", email: "a@b.co", password: "short" })?.message).toMatch(/at least 8/);
    expect(signUpProblem({ name: "Ana", email: "a@b.co", password: "longenough" })).toBeNull();
  });

  it("doesn't apply the length rule when logging in", () => {
    expect(logInProblem({ email: "a@b.co", password: "x" })).toBeNull();
    expect(logInProblem({ email: "a@b.co", password: "" })?.field).toBe("password");
  });
});

describe("demo accounts", () => {
  it("signs up, stays logged in, logs out and logs back in", async () => {
    const store = memoryStore();
    const client = createDemoAuth(store);
    const user = await client.signUp({ name: " Ana ", email: "Ana@Example.com", password: "correct horse" });
    expect(user).toMatchObject({ name: "Ana", email: "ana@example.com" });

    // A fresh client (a page refresh) still knows who is logged in.
    expect(await createDemoAuth(store).current()).toEqual(user);

    await client.logOut();
    expect(await client.current()).toBeNull();
    expect(await client.logIn({ email: "ana@example.com", password: "correct horse" })).toEqual(user);
  });

  it("never stores the password itself", async () => {
    const store = memoryStore();
    await createDemoAuth(store).signUp({ name: "Ana", email: "ana@example.com", password: "correct horse" });
    expect([...store.data.values()].join(" ")).not.toContain("correct horse");
  });

  it("rejects a wrong password and an unknown email with the same message", async () => {
    const client = createDemoAuth(memoryStore());
    await client.signUp({ name: "Ana", email: "ana@example.com", password: "correct horse" });
    await client.logOut();
    const wrong = await client.logIn({ email: "ana@example.com", password: "wrong pass" }).catch((e) => e);
    const unknown = await client.logIn({ email: "bo@example.com", password: "correct horse" }).catch((e) => e);
    expect(wrong).toBeInstanceOf(AuthError);
    expect(wrong.message).toBe(unknown.message);
  });

  it("refuses a second account with the same email", async () => {
    const client = createDemoAuth(memoryStore());
    await client.signUp({ name: "Ana", email: "ana@example.com", password: "correct horse" });
    await expect(
      client.signUp({ name: "Ana 2", email: "ANA@example.com", password: "another one" }),
    ).rejects.toMatchObject({ field: "email" });
  });
});

describe("server accounts", () => {
  it("keeps the session token and sends it as a bearer token", async () => {
    const store = memoryStore();
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/login")) {
        expect(JSON.parse(String(init?.body))).toEqual({ email: "ana@example.com", password: "pw" });
        return Response.json({ user: { id: "u1", name: "Ana", email: "ana@example.com" }, token: "tok" });
      }
      if (url.endsWith("/auth/me")) {
        expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer tok");
        return Response.json({ id: "u1", name: "Ana", email: "ana@example.com" });
      }
      return new Response(null, { status: 204 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = createServerAuth(store, "http://api");
    await client.logIn({ email: " Ana@example.com", password: "pw" });
    expect(await client.current()).toMatchObject({ id: "u1" });
    expect(client.authHeaders()).toEqual({ Authorization: "Bearer tok" });

    await client.logOut();
    expect(store.data.has("wanderwise.token")).toBe(false);
  });

  it("shows the server's message on the right field", async () => {
    vi.stubGlobal("fetch", async () =>
      Response.json({ detail: { field: "email", message: "That email is already registered." } }, { status: 409 }),
    );
    const client = createServerAuth(memoryStore(), "http://api");
    await expect(client.signUp({ name: "Ana", email: "ana@example.com", password: "longenough" })).rejects.toMatchObject({
      field: "email",
      message: "That email is already registered.",
    });
  });

  it("forgets an expired token", async () => {
    const store = memoryStore();
    store.setItem("wanderwise.token", "old");
    vi.stubGlobal("fetch", async () => new Response(null, { status: 401 }));
    expect(await createServerAuth(store, "http://api").current()).toBeNull();
    expect(store.data.has("wanderwise.token")).toBe(false);
  });
});
