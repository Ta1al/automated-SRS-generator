"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { ThemeToggle } from "@/components/theme-toggle";
import { extractHttpErrorMessage } from "@/lib/http";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);

  useEffect(() => {
    setIsHydrated(true);
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, password }),
      });

      if (!response.ok) {
        throw new Error(await extractHttpErrorMessage(response, "Login failed."));
      }

      router.push("/chat");
      router.refresh();
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Login failed.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="relative mx-auto flex min-h-screen w-full max-w-6xl items-center px-6 py-10">
      <div className="absolute top-6 right-6">
        <ThemeToggle size="sm" />
      </div>

      <div className="grid w-full gap-6 md:grid-cols-[1.1fr_1fr]">
        <section className="hidden rounded-3xl border border-[color:var(--outline-variant)]/30 bg-[color:var(--surface-lowest)]/70 p-10 shadow-[0_20px_45px_var(--shadow-color)] backdrop-blur md:block">
          <p className="text-xs font-semibold tracking-[0.22em] text-[color:var(--on-surface-variant)] uppercase">Welcome Back</p>
          <h1 className="mt-5 font-headline text-4xl font-semibold leading-tight text-[color:var(--primary)]">
            Continue refining your SRS drafts.
          </h1>
          <p className="mt-4 font-body text-lg text-[color:var(--on-surface-variant)]">
            Your latest chats, section revisions, and generated diagrams will be ready as soon as you sign in.
          </p>
        </section>

        <div className="app-panel w-full rounded-3xl p-8 md:p-10">
          <h2 className="font-headline text-2xl font-semibold text-[color:var(--primary)]">Log in</h2>
          <p className="mt-2 text-sm text-[color:var(--on-surface-variant)]">Access your SRS workspace and continue where you left off.</p>

          {isHydrated ? (
            <form onSubmit={onSubmit} className="mt-6 space-y-4">
              <label className="block text-sm font-medium text-[color:var(--on-surface-variant)]">
                <span>Email</span>
                <input
                  className="field-input mt-1 w-full rounded-xl px-3 py-2 ring-1 ring-[color:var(--outline-variant)]/50 outline-none"
                  type="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  autoComplete="email"
                  data-lpignore="true"
                  data-1p-ignore="true"
                />
              </label>

              <label className="block text-sm font-medium text-[color:var(--on-surface-variant)]">
                <span>Password</span>
                <input
                  className="field-input mt-1 w-full rounded-xl px-3 py-2 ring-1 ring-[color:var(--outline-variant)]/50 outline-none"
                  type="password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  data-lpignore="true"
                  data-1p-ignore="true"
                />
              </label>

              {error ? <p role="alert" className="error-banner rounded-xl px-3 py-2 text-sm">{error}</p> : null}

              <button
                type="submit"
                disabled={isLoading}
                className="w-full rounded-xl bg-[color:var(--primary)] px-3 py-2 text-sm font-semibold text-[color:var(--on-primary)] transition-transform hover:-translate-y-0.5 disabled:opacity-60"
              >
                {isLoading ? "Signing you in..." : "Login"}
              </button>
            </form>
          ) : (
            <div aria-hidden="true" className="mt-6 space-y-4">
              <div className="h-14 w-full rounded-xl bg-[color:var(--surface-low)]/70" />
              <div className="h-14 w-full rounded-xl bg-[color:var(--surface-low)]/70" />
              <div className="h-10 w-full rounded-xl bg-[color:var(--surface-low)]/70" />
            </div>
          )}

          <p className="mt-4 text-sm text-[color:var(--on-surface-variant)]">
            No account? <Link className="underline decoration-dotted underline-offset-4" href="/signup">Create one</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
