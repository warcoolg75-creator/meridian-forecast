import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useAuth } from "../auth/auth-context";
import { ForecastArt } from "../components/brand/ForecastArt";
import { AlertIcon, Spinner } from "../components/brand/icons";
import { Wordmark } from "../components/brand/Wordmark";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { DEMO_ACCOUNTS, type DemoAccount } from "./login/demoAccounts";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function emailError(value: string): string | undefined {
  if (!value.trim()) return "Enter your email address.";
  if (!EMAIL_PATTERN.test(value.trim()))
    return "Enter a valid email address, like name@company.com.";
  return undefined;
}

function passwordError(value: string): string | undefined {
  return value ? undefined : "Enter your password.";
}

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [touched, setTouched] = useState({ email: false, password: false });
  const [submitting, setSubmitting] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  const errors = { email: emailError(email), password: passwordError(password) };

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setTouched({ email: true, password: true });
    if (errors.email || errors.password) {
      document.getElementById(errors.email ? "login-email" : "login-password")?.focus();
      return;
    }
    setBanner(null);
    setSubmitting(true);
    const result = await login(email.trim(), password, remember);
    if (!result.ok) {
      setSubmitting(false);
      setBanner(result.message);
    }
    // On success the session exists and <RedirectIfSignedIn> navigates away.
  }

  function fillDemo(account: DemoAccount) {
    setEmail(account.email);
    setPassword(account.password);
    setTouched({ email: false, password: false });
    setBanner(null);
  }

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-5">
      {/* Phones: a short header band. lg and up: the left 60%. */}
      <aside className="relative overflow-hidden bg-maroon-900 px-4 py-8 sm:px-6 lg:col-span-3 lg:flex lg:flex-col lg:justify-between lg:p-12">
        <ForecastArt
          tone="dark"
          className="pointer-events-none absolute -right-16 -bottom-8 w-full max-w-3xl opacity-10 lg:top-24 lg:right-0 lg:bottom-auto lg:opacity-20"
        />
        <Link
          to="/"
          aria-label="Meridian home"
          className="relative self-start focus-visible:outline-cream-50"
        >
          <Wordmark tone="cream" />
        </Link>
        <p className="relative mt-3 max-w-md text-step-n1 text-maroon-100 lg:mt-0 lg:max-w-lg lg:font-display lg:text-step-4 lg:text-cream-50">
          Forecast demand. Plan production. See the confidence behind every number.
        </p>
      </aside>

      <main className="flex items-center justify-center px-4 py-12 sm:px-6 lg:col-span-2 lg:py-16">
        <div className="w-full max-w-sm space-y-8">
          <div className="space-y-2">
            <h1 className="text-step-4">Sign in</h1>
            <p className="text-fg-muted">Welcome back. Sign in with your work email.</p>
          </div>

          {banner && (
            <div
              role="alert"
              className="flex gap-3 rounded-control border border-negative bg-negative-subtle p-3 text-step-n1 text-negative"
            >
              <AlertIcon className="size-5 shrink-0" />
              <p>{banner}</p>
            </div>
          )}

          <form noValidate onSubmit={submit} className="space-y-5">
            <Input
              id="login-email"
              label="Email"
              type="email"
              inputMode="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              onBlur={() => setTouched((t) => ({ ...t, email: true }))}
              error={touched.email ? errors.email : undefined}
            />
            <Input
              id="login-password"
              label="Password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              onBlur={() => setTouched((t) => ({ ...t, password: true }))}
              error={touched.password ? errors.password : undefined}
              trailing={
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="h-8 rounded-control px-3 text-step-n2 font-medium text-primary hover:bg-primary-subtle"
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              }
            />
            <label className="flex items-center gap-2 text-step-n1 text-fg">
              <input
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.target.checked)}
                className="size-4 accent-primary"
              />
              Remember me
            </label>
            <Button type="submit" className="w-full" aria-busy={submitting || undefined}>
              {submitting ? (
                <>
                  <Spinner /> Signing in…
                </>
              ) : (
                "Sign in"
              )}
            </Button>
          </form>

          {import.meta.env.DEV && DEMO_ACCOUNTS.length > 0 && (
            <div className="space-y-3 border-t border-line pt-6">
              <p className="text-step-n1 font-medium text-fg">Use demo account</p>
              <div className="flex flex-wrap gap-2">
                {DEMO_ACCOUNTS.map((account) => (
                  <Button
                    key={account.email}
                    variant="secondary"
                    size="sm"
                    onClick={() => fillDemo(account)}
                  >
                    {account.label}
                  </Button>
                ))}
              </div>
              <p className="text-step-n2 text-fg-muted">
                Development builds only. Fills in the form; then press Sign in.
              </p>
            </div>
          )}

          <p className="text-step-n1">
            <Link to="/" className="text-primary underline-offset-4 hover:underline">
              ← Back to the home page
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}
