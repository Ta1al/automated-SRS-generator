"use client";

import { ThemeToggle } from "@/components/theme-toggle";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="relative flex min-h-screen items-center justify-center px-6 py-10">
      <div className="absolute top-6 right-6">
        <ThemeToggle size="sm" />
      </div>

      <div className="app-panel w-full max-w-xl rounded-3xl p-8 text-center">
        <p className="text-xs font-semibold tracking-[0.2em] text-[color:var(--on-surface-variant)] uppercase">
          Something went wrong
        </p>
        <h1 className="mt-3 font-headline text-3xl font-semibold text-[color:var(--primary)]">
          We could not finish that request.
        </h1>
        <p className="mt-3 text-sm text-[color:var(--on-surface-variant)]">
          {error.message || "An unexpected error occurred. Please try again."}
        </p>
        <div className="mt-6 flex justify-center gap-2">
          <button
            type="button"
            onClick={reset}
            className="rounded-full bg-[color:var(--primary)] px-4 py-2 text-sm font-semibold text-[color:var(--on-primary)]"
          >
            Try again
          </button>
        </div>
      </div>
    </div>
  );
}