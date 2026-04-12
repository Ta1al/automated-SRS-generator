import Link from "next/link";

import { ThemeToggle } from "@/components/theme-toggle";

export default function Home() {
  return (
    <div className="min-h-screen text-[color:var(--foreground)]">
      <header className="sticky top-0 z-40 border-b border-[color:var(--outline-variant)]/35 bg-[color:var(--surface-lowest)]/88 px-6 py-4 backdrop-blur-lg">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between">
          <h1 className="font-headline text-xl font-bold tracking-tight text-[color:var(--primary)]">Proscript Ledger</h1>
          <div className="flex items-center gap-2">
            <ThemeToggle size="sm" />
            <Link className="rounded-full border border-[color:var(--outline-variant)]/65 px-4 py-2 text-sm font-medium transition-colors hover:bg-[color:var(--surface-low)]" href="/login">Login</Link>
            <Link className="rounded-full bg-[color:var(--primary)] px-4 py-2 text-sm font-semibold text-[color:var(--on-primary)] transition-transform hover:-translate-y-0.5" href="/signup">Get Started</Link>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-6 py-14 md:py-20">
        <section className="relative overflow-hidden rounded-[2rem] border border-[color:var(--outline-variant)]/35 bg-[color:var(--surface-lowest)]/75 px-6 py-12 text-center shadow-[0_22px_50px_var(--shadow-color)] backdrop-blur md:px-12 md:py-16">
          <div className="absolute -top-16 -left-14 h-40 w-40 rounded-full bg-[color:var(--primary)]/18 blur-2xl" />
          <div className="absolute -right-8 -bottom-16 h-40 w-40 rounded-full bg-[color:var(--surface-highest)]/85 blur-2xl" />

          <p className="font-label text-xs font-semibold tracking-[0.23em] text-[color:var(--on-surface-variant)] uppercase">Requirements Engineering Assistant</p>
          <h2 className="mx-auto mt-6 max-w-4xl font-headline text-4xl font-bold leading-tight text-[color:var(--primary)] md:text-6xl">
            Ship Better Specs Faster, With Less Rework.
          </h2>
          <p className="font-body mx-auto mt-6 max-w-3xl text-lg text-[color:var(--on-surface-variant)] md:text-xl">
            Move from rough idea to structured SRS through guided discovery, live section drafting, diagram generation, and one-click DOCX export.
          </p>
          <div className="mt-9 flex flex-col justify-center gap-3 sm:flex-row">
            <Link className="rounded-full bg-gradient-to-r from-[color:var(--primary)] to-[color:var(--primary-container)] px-8 py-3 text-sm font-semibold text-[color:var(--on-primary)] shadow-[0_10px_20px_var(--shadow-color)] transition-transform hover:-translate-y-0.5" href="/signup">Start a New SRS</Link>
            <Link className="rounded-full border border-[color:var(--outline-variant)]/70 bg-[color:var(--surface-low)] px-8 py-3 text-sm font-semibold text-[color:var(--primary)] transition-colors hover:bg-[color:var(--surface-highest)]" href="/chat">Open Workspace</Link>
          </div>
        </section>

        <section className="mt-10 grid gap-6 md:grid-cols-3">
          <article className="app-panel stagger-enter rounded-2xl p-6" style={{ animationDelay: "20ms" }}>
            <p className="text-[10px] font-semibold tracking-[0.16em] text-[color:var(--on-surface-variant)] uppercase">01</p>
            <h3 className="mt-2 font-headline text-lg font-semibold">Describe</h3>
            <p className="mt-3 text-sm text-[color:var(--on-surface-variant)]">Explain your product idea in plain language and let the assistant identify what is still unclear.</p>
          </article>
          <article className="app-panel stagger-enter rounded-2xl p-6" style={{ animationDelay: "60ms" }}>
            <p className="text-[10px] font-semibold tracking-[0.16em] text-[color:var(--on-surface-variant)] uppercase">02</p>
            <h3 className="mt-2 font-headline text-lg font-semibold">Generate</h3>
            <p className="mt-3 text-sm text-[color:var(--on-surface-variant)]">Draft requirements sections in parallel with compliance-aware structure and contextual guidance.</p>
          </article>
          <article className="app-panel stagger-enter rounded-2xl p-6" style={{ animationDelay: "100ms" }}>
            <p className="text-[10px] font-semibold tracking-[0.16em] text-[color:var(--on-surface-variant)] uppercase">03</p>
            <h3 className="mt-2 font-headline text-lg font-semibold">Refine</h3>
            <p className="mt-3 text-sm text-[color:var(--on-surface-variant)]">Select any part for targeted revisions, then export a polished document once the draft is complete.</p>
          </article>
        </section>
      </main>
    </div>
  );
}
