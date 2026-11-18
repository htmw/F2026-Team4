import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { auth as defaultAuth, AuthError, MIN_PASSWORD_LENGTH } from "./auth";
import type { AuthClient, AuthField, User } from "./auth";

interface Props {
  onLoggedIn: (user: User) => void;
  onCancel: () => void;
  // Why the person was sent here, e.g. to save the plan on screen.
  reason?: string | null;
  client?: AuthClient;
}

type Mode = "login" | "signup";

export function LoginPage({ onLoggedIn, onCancel, reason, client = defaultAuth }: Props) {
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<{ message: string; field?: AuthField } | null>(null);
  const [busy, setBusy] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const fieldRefs = {
    name: useRef<HTMLInputElement>(null),
    email: useRef<HTMLInputElement>(null),
    password: useRef<HTMLInputElement>(null),
  };

  useEffect(() => {
    headingRef.current?.focus();
  }, [mode]);

  useEffect(() => {
    if (error?.field) fieldRefs[error.field].current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [error]);

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user =
        mode === "signup"
          ? await client.signUp({ name, email, password })
          : await client.logIn({ email, password });
      onLoggedIn(user);
    } catch (err) {
      if (err instanceof AuthError) setError({ message: err.message, field: err.field });
      else setError({ message: "Couldn't reach your account right now. Try again." });
    } finally {
      setBusy(false);
    }
  }

  const fieldError = (field: AuthField) =>
    error?.field === field ? (
      <p id={`auth-${field}-error`} className="field-error" role="alert">
        {error.message}
      </p>
    ) : null;
  const invalid = (field: AuthField) => (error?.field === field ? true : undefined);
  const describedBy = (field: AuthField, hint?: string) =>
    [error?.field === field ? `auth-${field}-error` : null, hint].filter(Boolean).join(" ") || undefined;

  const signup = mode === "signup";

  return (
    <section className="panel auth-panel" aria-labelledby="auth-title">
      <h2 id="auth-title" ref={headingRef} tabIndex={-1} className="panel-title">
        {signup ? "Create your account" : "Log in"}
      </h2>
      <p className="auth-lead">
        {reason ?? "Log in to save your trips and open them again from any visit."}
      </p>

      <form onSubmit={handleSubmit} noValidate className="auth-form">
        <fieldset disabled={busy}>
          <legend className="visually-hidden">{signup ? "Account details" : "Log-in details"}</legend>
          {signup && (
            <div className="field">
              <label htmlFor="auth-name">Name</label>
              <input
                id="auth-name"
                ref={fieldRefs.name}
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                aria-invalid={invalid("name")}
                aria-describedby={describedBy("name")}
              />
              {fieldError("name")}
            </div>
          )}
          <div className="field">
            <label htmlFor="auth-email">Email</label>
            <input
              id="auth-email"
              ref={fieldRefs.email}
              type="email"
              autoComplete="email"
              inputMode="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-invalid={invalid("email")}
              aria-describedby={describedBy("email")}
            />
            {fieldError("email")}
          </div>
          <div className="field">
            <label htmlFor="auth-password">Password</label>
            <div className="password-row">
              <input
                id="auth-password"
                ref={fieldRefs.password}
                type={showPassword ? "text" : "password"}
                autoComplete={signup ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={invalid("password")}
                aria-describedby={describedBy("password", signup ? "auth-password-hint" : undefined)}
              />
              <button
                type="button"
                className="button-quiet button-small"
                aria-pressed={showPassword}
                onClick={() => setShowPassword((s) => !s)}
              >
                {showPassword ? "Hide" : "Show"}
                <span className="visually-hidden"> password</span>
              </button>
            </div>
            {signup && (
              <p id="auth-password-hint" className="field-hint">
                At least {MIN_PASSWORD_LENGTH} characters.
              </p>
            )}
            {fieldError("password")}
          </div>
          {error && !error.field && (
            <p className="field-error" role="alert">
              {error.message}
            </p>
          )}
          <div className="auth-actions">
            <button type="submit" className="button-primary">
              {busy ? (signup ? "Creating account…" : "Logging in…") : signup ? "Create account" : "Log in"}
            </button>
            <button type="button" className="button-quiet" onClick={onCancel}>
              Back to planner
            </button>
          </div>
        </fieldset>
      </form>

      <p className="auth-switch">
        {signup ? "Already have an account? " : "New to Wanderwise? "}
        <button type="button" className="link-button" onClick={() => switchMode(signup ? "login" : "signup")}>
          {signup ? "Log in" : "Create an account"}
        </button>
      </p>

      {client.mode === "demo" && (
        <p className="auth-demo-note">
          Demo accounts: your account and saved-trip list are kept in this browser only, until
          accounts move to the Wanderwise server.
        </p>
      )}
    </section>
  );
}
