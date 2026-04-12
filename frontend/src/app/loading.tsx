export default function GlobalLoading() {
  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="app-panel w-full max-w-lg rounded-3xl p-8 text-center">
        <p className="text-xs font-semibold tracking-[0.2em] text-[color:var(--on-surface-variant)] uppercase">
          Loading
        </p>
        <h1 className="mt-3 font-headline text-2xl font-semibold text-[color:var(--primary)]">
          Preparing your workspace...
        </h1>
        <p className="mt-2 text-sm text-[color:var(--on-surface-variant)]">
          Fetching your latest drafts and conversation history.
        </p>
        <div className="mt-6 h-2 overflow-hidden rounded-full bg-[color:var(--surface-low)]">
          <div className="h-full w-1/2 animate-pulse rounded-full bg-[color:var(--primary)]" />
        </div>
      </div>
    </div>
  );
}