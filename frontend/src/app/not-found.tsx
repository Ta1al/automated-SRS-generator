import Link from "next/link";

import { ThemeToggle } from "@/components/theme-toggle";

export default function NotFoundPage() {
  return (
    <div className="relative flex min-h-screen items-center justify-center px-6 py-10">
      <div className="absolute top-6 right-6">
        <ThemeToggle size="sm" />
      </div>

      <div className="app-panel w-full max-w-xl rounded-3xl p-8 text-center">
        <p className="text-xs font-semibold tracking-[0.2em] text-[color:var(--on-surface-variant)] uppercase">
          404
        </p>
        <h1 className="mt-3 font-headline text-3xl font-semibold text-[color:var(--primary)]">
          This page was not found.
        </h1>
        <p className="mt-3 text-sm text-[color:var(--on-surface-variant)]">
          The URL may be outdated, or the page may have been moved.
        </p>
        <div className="mt-6 flex justify-center gap-2">
          <Link
            href="/"
            className="rounded-full border border-[color:var(--outline-variant)]/60 px-4 py-2 text-sm font-medium transition-colors hover:bg-[color:var(--surface-low)]"
          >
            Go Home
          </Link>
          <Link
            href="/chat"
            className="rounded-full bg-[color:var(--primary)] px-4 py-2 text-sm font-semibold text-[color:var(--on-primary)]"
          >
            Open Chat
          </Link>
        </div>
      </div>
    </div>
  );
}