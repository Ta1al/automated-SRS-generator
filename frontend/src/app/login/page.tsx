"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

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
        const payload = await response.json();
        throw new Error(payload.error || "Login failed.");
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
    <div className="mx-auto flex min-h-screen w-full max-w-md items-center px-6">
      <div className="app-panel w-full rounded-xl p-8">
        <h1 className="font-headline text-2xl font-semibold text-[color:var(--primary)]">Login</h1>
        <p className="mt-2 text-sm text-[color:var(--on-surface-variant)]">Continue your SRS session.</p>

        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <label className="block text-sm font-medium text-[color:var(--on-surface-variant)]">
            <span>Email</span>
            <input
              className="mt-1 w-full rounded-md bg-[color:var(--surface-low)] px-3 py-2 ring-1 ring-[color:var(--outline-variant)]/40 outline-none focus:ring-2 focus:ring-[color:var(--primary)]"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              suppressHydrationWarning
            />
          </label>

          <label className="block text-sm font-medium text-[color:var(--on-surface-variant)]">
            <span>Password</span>
            <input
              className="mt-1 w-full rounded-md bg-[color:var(--surface-low)] px-3 py-2 ring-1 ring-[color:var(--outline-variant)]/40 outline-none focus:ring-2 focus:ring-[color:var(--primary)]"
              type="password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              suppressHydrationWarning
            />
          </label>

          {error ? <p className="text-sm text-red-600">{error}</p> : null}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded-md bg-[color:var(--primary)] px-3 py-2 text-white disabled:opacity-60"
          >
            {isLoading ? "Logging in..." : "Login"}
          </button>
        </form>

        <p className="mt-4 text-sm text-[color:var(--on-surface-variant)]">
          No account? <Link className="underline" href="/signup">Create one</Link>
        </p>
      </div>
    </div>
  );
}
