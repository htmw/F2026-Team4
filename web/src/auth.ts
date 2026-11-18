// Accounts: sign up, log in, log out, and "who is logged in".
//
// Two interchangeable clients behind one interface, chosen by VITE_AUTH_MODE:
// - "demo" (the default): accounts live in this browser's localStorage, with the password
//   hashed (PBKDF2). It lets the UI work end to end before the backend has accounts. It is
//   NOT real security: anyone with access to the browser can read or reset the data.
// - "server": the backend's /auth endpoints (see web/BACKEND-HANDOFF.md). The backend
//   returns a session token, sent as "Authorization: Bearer <token>" on later requests.
// The UI only talks to `auth`, so switching to the server needs no UI change.

import { API_BASE } from "./api";

export interface User {
  id: string;
  name: string;
  email: string;
}

export interface SignUpInput {
  name: string;
  email: string;
  password: string;
}

export interface LogInInput {
  email: string;
  password: string;
}

export type AuthField = "name" | "email" | "password";

// A problem the person can fix; `field` says which input to show it on.
export class AuthError extends Error {
  constructor(
    message: string,
    readonly field?: AuthField,
  ) {
    super(message);
    this.name = "AuthError";
  }
}

export interface AuthClient {
  readonly mode: "demo" | "server";
  current(): Promise<User | null>;
  signUp(input: SignUpInput): Promise<User>;
  logIn(input: LogInInput): Promise<User>;
  logOut(): Promise<void>;
  // Headers that identify the logged-in user to the backend ({} in demo mode).
  authHeaders(): Record<string, string>;
}

export const MIN_PASSWORD_LENGTH = 8;

/** The first problem with a sign-up form, checked before anything is sent. */
export function signUpProblem({ name, email, password }: SignUpInput): AuthError | null {
  if (!name.trim()) return new AuthError("Enter your name.", "name");
  return logInProblem({ email, password }) ?? passwordProblem(password);
}

/** The first problem with a log-in form. */
export function logInProblem({ email, password }: LogInInput): AuthError | null {
  if (!email.trim()) return new AuthError("Enter your email address.", "email");
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
    return new AuthError("Enter an email address like name@example.com.", "email");
  }
  if (!password) return new AuthError("Enter your password.", "password");
  return null;
}

function passwordProblem(password: string): AuthError | null {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return new AuthError(`Use at least ${MIN_PASSWORD_LENGTH} characters for your password.`, "password");
  }
  return null;
}

function normaliseEmail(email: string): string {
  return email.trim().toLowerCase();
}

// localStorage can be missing or throw (private windows, blocked storage); treat that as empty.
export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export function browserStore(): KeyValueStore {
  const memory = new Map<string, string>();
  const ls = (): Storage | null => {
    try {
      return window.localStorage;
    } catch {
      return null;
    }
  };
  return {
    getItem(key) {
      try {
        return ls()?.getItem(key) ?? memory.get(key) ?? null;
      } catch {
        return memory.get(key) ?? null;
      }
    },
    setItem(key, value) {
      memory.set(key, value);
      try {
        ls()?.setItem(key, value);
      } catch {
        // Kept in memory for this page only.
      }
    },
    removeItem(key) {
      memory.delete(key);
      try {
        ls()?.removeItem(key);
      } catch {
        // Nothing stored to remove.
      }
    },
  };
}

export function readJson<T>(store: KeyValueStore, key: string, fallback: T): T {
  const raw = store.getItem(key);
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

// ---- Demo mode: accounts in this browser ----

interface DemoAccount {
  id: string;
  name: string;
  email: string;
  salt: string;
  hash: string;
}

const USERS_KEY = "wanderwise.demo.users";
const SESSION_KEY = "wanderwise.demo.session";

function toHex(bytes: ArrayBuffer | Uint8Array): string {
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function hashPassword(password: string, salt: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, [
    "deriveBits",
  ]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: new TextEncoder().encode(salt), iterations: 100_000 },
    key,
    256,
  );
  return toHex(bits);
}

function publicUser(account: DemoAccount): User {
  return { id: account.id, name: account.name, email: account.email };
}

export function createDemoAuth(store: KeyValueStore = browserStore()): AuthClient {
  const accounts = () => readJson<Record<string, DemoAccount>>(store, USERS_KEY, {});

  return {
    mode: "demo",
    async current() {
      const email = store.getItem(SESSION_KEY);
      const account = email ? accounts()[email] : undefined;
      return account ? publicUser(account) : null;
    },
    async signUp(input) {
      const problem = signUpProblem(input);
      if (problem) throw problem;
      const email = normaliseEmail(input.email);
      const all = accounts();
      if (all[email]) {
        throw new AuthError("There's already an account with this email. Log in instead.", "email");
      }
      const salt = toHex(crypto.getRandomValues(new Uint8Array(16)));
      const account: DemoAccount = {
        id: crypto.randomUUID(),
        name: input.name.trim(),
        email,
        salt,
        hash: await hashPassword(input.password, salt),
      };
      store.setItem(USERS_KEY, JSON.stringify({ ...all, [email]: account }));
      store.setItem(SESSION_KEY, email);
      return publicUser(account);
    },
    async logIn(input) {
      const problem = logInProblem(input);
      if (problem) throw problem;
      const email = normaliseEmail(input.email);
      const account = accounts()[email];
      // The same message for an unknown email and a wrong password, as a real server would.
      if (!account || (await hashPassword(input.password, account.salt)) !== account.hash) {
        throw new AuthError("That email and password don't match an account.", "password");
      }
      store.setItem(SESSION_KEY, email);
      return publicUser(account);
    },
    async logOut() {
      store.removeItem(SESSION_KEY);
    },
    authHeaders() {
      return {};
    },
  };
}

// ---- Server mode: the backend's /auth endpoints ----

const TOKEN_KEY = "wanderwise.token";

interface SessionResponse {
  user: User;
  token: string;
}

// Turn a backend error ({"detail": "..."} or {"detail": {"field": "email", "message": "..."}})
// into an AuthError on the right field.
async function authFailure(resp: Response): Promise<AuthError> {
  let detail: unknown;
  try {
    detail = ((await resp.json()) as { detail?: unknown }).detail;
  } catch {
    detail = undefined;
  }
  if (typeof detail === "string" && detail) return new AuthError(detail);
  if (detail && typeof detail === "object") {
    const { field, message } = detail as { field?: string; message?: string };
    const known = field === "name" || field === "email" || field === "password" ? field : undefined;
    if (message) return new AuthError(message, known);
  }
  if (resp.status === 401) return new AuthError("That email and password don't match an account.", "password");
  if (resp.status === 409) return new AuthError("There's already an account with this email. Log in instead.", "email");
  return new AuthError(`Couldn't reach your account right now (error ${resp.status}). Try again.`);
}

export function createServerAuth(store: KeyValueStore = browserStore(), base: string = API_BASE): AuthClient {
  const headers = (): Record<string, string> => {
    const token = store.getItem(TOKEN_KEY);
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  async function start(path: string, body: object): Promise<User> {
    const resp = await fetch(`${base}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw await authFailure(resp);
    const session = (await resp.json()) as SessionResponse;
    store.setItem(TOKEN_KEY, session.token);
    return session.user;
  }

  return {
    mode: "server",
    async current() {
      if (!store.getItem(TOKEN_KEY)) return null;
      const resp = await fetch(`${base}/auth/me`, { headers: headers() });
      if (resp.status === 401) {
        store.removeItem(TOKEN_KEY);
        return null;
      }
      if (!resp.ok) throw await authFailure(resp);
      return (await resp.json()) as User;
    },
    async signUp(input) {
      const problem = signUpProblem(input);
      if (problem) throw problem;
      return start("/auth/signup", { name: input.name.trim(), email: normaliseEmail(input.email), password: input.password });
    },
    async logIn(input) {
      const problem = logInProblem(input);
      if (problem) throw problem;
      return start("/auth/login", { email: normaliseEmail(input.email), password: input.password });
    },
    async logOut() {
      const auth = headers();
      store.removeItem(TOKEN_KEY);
      // Best effort: the token is already forgotten here even if the server can't be reached.
      await fetch(`${base}/auth/logout`, { method: "POST", headers: auth }).catch(() => undefined);
    },
    authHeaders: headers,
  };
}

export const auth: AuthClient =
  import.meta.env.VITE_AUTH_MODE === "server" ? createServerAuth() : createDemoAuth();
