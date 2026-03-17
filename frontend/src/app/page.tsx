import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen bg-zinc-50 px-6 py-8 md:py-10">
      <main className="mx-auto w-full max-w-6xl">
        <header className="flex items-center justify-between rounded-2xl border border-black/10 bg-white px-4 py-3 md:px-6">
          <h1 className="text-base font-semibold md:text-lg">AI SRS Generator</h1>
          <div className="space-x-2">
            <Link
              className="rounded-md border border-black/15 px-3 py-1.5 text-sm font-medium"
              href="/login"
            >
              Login
            </Link>
            <Link
              className="rounded-md bg-black px-3 py-1.5 text-sm font-medium text-white"
              href="/signup"
            >
              Sign up
            </Link>
          </div>
        </header>

        <section className="mt-8 rounded-3xl border border-black/10 bg-white p-6 md:p-10">
          <p className="inline-flex rounded-full border border-black/10 bg-zinc-100 px-3 py-1 text-xs font-semibold tracking-wide text-black/70 uppercase">
            Requirements Engineering Assistant
          </p>

          <div className="mt-5 grid gap-8 md:grid-cols-[1.2fr_0.8fr] md:items-end">
            <div>
              <h2 className="max-w-3xl text-3xl font-semibold leading-tight md:text-5xl">
                Turn rough product ideas into clear, structured SRS documents.
              </h2>
              <p className="mt-4 max-w-2xl text-base text-black/70 md:text-lg">
                Collaborate with an AI elicitation assistant, refine requirements step by step,
                and keep your evolving SRS visible in one unified workspace.
              </p>

              <div className="mt-7 flex flex-wrap gap-3">
                <Link className="rounded-md bg-black px-5 py-2.5 text-sm font-medium text-white" href="/signup">
                  Start building
                </Link>
                <Link
                  className="rounded-md border border-black/15 bg-white px-5 py-2.5 text-sm font-medium"
                  href="/chat"
                >
                  Open chat workspace
                </Link>
              </div>
            </div>

            <div className="rounded-2xl border border-black/10 bg-zinc-50 p-5">
              <h3 className="text-sm font-semibold">Why teams use it</h3>
              <ul className="mt-4 space-y-3 text-sm text-black/70">
                <li className="rounded-lg border border-black/10 bg-white px-3 py-2">
                  Guided elicitation to reduce missing requirements.
                </li>
                <li className="rounded-lg border border-black/10 bg-white px-3 py-2">
                  Persistent chat history for iterative refinement.
                </li>
                <li className="rounded-lg border border-black/10 bg-white px-3 py-2">
                  Live document and state visibility during drafting.
                </li>
              </ul>
            </div>
          </div>
        </section>

        <section className="mt-8 grid gap-4 md:grid-cols-3">
          <article className="rounded-2xl border border-black/10 bg-white p-5">
            <h3 className="text-base font-semibold">Authenticated workspace</h3>
            <p className="mt-2 text-sm text-black/70">
              Each user keeps a private list of chat sessions tied to the shared PostgreSQL database.
            </p>
          </article>
          <article className="rounded-2xl border border-black/10 bg-white p-5">
            <h3 className="text-base font-semibold">Continuous SRS conversation</h3>
            <p className="mt-2 text-sm text-black/70">
              Resume prior threads, send new prompts, and keep all messages ordered in one timeline.
            </p>
          </article>
          <article className="rounded-2xl border border-black/10 bg-white p-5">
            <h3 className="text-base font-semibold">Live document visibility</h3>
            <p className="mt-2 text-sm text-black/70">
              View backend state plus the current generated SRS document side by side with the chat.
            </p>
          </article>
        </section>

        <section className="mt-4 rounded-2xl border border-black/10 bg-white p-5 text-sm text-black/70 md:p-6">
          Move from idea to requirement baseline faster with one flow: define scope, clarify edge cases,
          and keep an auditable conversation linked directly to the generated SRS.
        </section>
      </main>
    </div>
  );
}
