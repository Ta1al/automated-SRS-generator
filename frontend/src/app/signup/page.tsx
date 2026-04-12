"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { ThemeToggle } from "@/components/theme-toggle";
import { extractHttpErrorMessage } from "@/lib/http";

export default function SignupPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      const response = await fetch("/api/auth/signup", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ name, email, password }),
      });

      if (!response.ok) {
        throw new Error(await extractHttpErrorMessage(response, "Signup failed."));
      }

      router.push("/chat");
      router.refresh();
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Signup failed.";
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
          <p className="text-xs font-semibold tracking-[0.22em] text-[color:var(--on-surface-variant)] uppercase">Create Workspace</p>
          <h1 className="mt-5 font-headline text-4xl font-semibold leading-tight text-[color:var(--primary)]">
            Build production-ready SRS documents with guided iteration.
          </h1>
          <p className="mt-4 font-body text-lg text-[color:var(--on-surface-variant)]">
            Draft requirements, answer clarification prompts, and refine targeted sections from a single collaborative workspace.
          </p>
        </section>

        <div className="app-panel w-full rounded-3xl p-8 md:p-10">
          <h2 className="font-headline text-2xl font-semibold text-[color:var(--primary)]">Sign up</h2>
          <p className="mt-2 text-sm text-[color:var(--on-surface-variant)]">Create your account to start generating and revising SRS drafts.</p>

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <label className="block text-sm font-medium text-[color:var(--on-surface-variant)]">
              <span>Name</span>
              <input
                className="field-input mt-1 w-full rounded-xl px-3 py-2 ring-1 ring-[color:var(--outline-variant)]/50 outline-none"
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoComplete="name"
              />
            </label>

            <label className="block text-sm font-medium text-[color:var(--on-surface-variant)]">
              <span>Email</span>
              <input
                className="field-input mt-1 w-full rounded-xl px-3 py-2 ring-1 ring-[color:var(--outline-variant)]/50 outline-none"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
              />
            </label>

            <label className="block text-sm font-medium text-[color:var(--on-surface-variant)]">
              <span>Password</span>
              <input
                className="field-input mt-1 w-full rounded-xl px-3 py-2 ring-1 ring-[color:var(--outline-variant)]/50 outline-none"
                type="password"
                minLength={8}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
              />
            </label>

            {error ? <p role="alert" className="error-banner rounded-xl px-3 py-2 text-sm">{error}</p> : null}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full rounded-xl bg-[color:var(--primary)] px-3 py-2 text-sm font-semibold text-[color:var(--on-primary)] transition-transform hover:-translate-y-0.5 disabled:opacity-60"
            >
              {isLoading ? "Creating your workspace..." : "Create account"}
            </button>
          </form>

          <p className="mt-4 text-sm text-[color:var(--on-surface-variant)]">
            Have an account? <Link className="underline decoration-dotted underline-offset-4" href="/login">Login</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
