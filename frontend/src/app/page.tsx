import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen bg-[color:var(--surface)] text-[color:var(--foreground)]">
      <header className="sticky top-0 z-40 border-b border-[color:var(--outline-variant)]/30 bg-white/90 px-6 py-4 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between">
          <h1 className="font-headline text-xl font-bold tracking-tight text-[color:var(--primary)]">Proscript Ledger</h1>
          <div className="flex gap-2">
            <Link className="rounded-md border border-[color:var(--outline-variant)] px-4 py-2 text-sm" href="/login">Login</Link>
            <Link className="rounded-md bg-[color:var(--primary)] px-4 py-2 text-sm font-semibold text-[color:var(--on-primary)]" href="/signup">Get Started</Link>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-6 py-20">
        <section className="text-center">
          <p className="font-label text-xs font-semibold tracking-[0.2em] text-[color:var(--on-surface-variant)] uppercase">Requirements Engineering Assistant</p>
          <h2 className="mx-auto mt-6 max-w-4xl font-headline text-5xl font-extrabold leading-tight text-[color:var(--primary)] md:text-7xl">
            From Vision to Technical Specification in Minutes.
          </h2>
          <p className="font-body mx-auto mt-6 max-w-3xl text-xl text-[color:var(--on-surface-variant)]">
            Generate complete, editable SRS documents through guided conversation, live drafting, and structured export.
          </p>
          <div className="mt-10 flex flex-col justify-center gap-3 sm:flex-row">
            <Link className="rounded-md bg-gradient-to-r from-[color:var(--primary)] to-[color:var(--primary-container)] px-8 py-3 text-sm font-semibold text-white" href="/signup">Generate Your SRS</Link>
            <Link className="rounded-md bg-[color:var(--surface-low)] px-8 py-3 text-sm font-semibold text-[color:var(--primary)]" href="/chat">Open Workspace</Link>
          </div>
        </section>

        <section className="mt-20 grid gap-6 md:grid-cols-3">
          <article className="app-panel rounded-xl p-6">
            <h3 className="font-headline text-lg font-semibold">Describe</h3>
            <p className="mt-3 text-sm text-[color:var(--on-surface-variant)]">Explain your product in plain language and let the assistant discover missing details.</p>
          </article>
          <article className="app-panel rounded-xl p-6">
            <h3 className="font-headline text-lg font-semibold">Generate</h3>
            <p className="mt-3 text-sm text-[color:var(--on-surface-variant)]">Draft sections in parallel with standards-aware structure and compliance context.</p>
          </article>
          <article className="app-panel rounded-xl p-6">
            <h3 className="font-headline text-lg font-semibold">Refine</h3>
            <p className="mt-3 text-sm text-[color:var(--on-surface-variant)]">Edit targeted sections, review history, and export polished DOCX output.</p>
          </article>
        </section>
      </main>
    </div>
  );
}
