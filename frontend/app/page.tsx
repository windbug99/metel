import AuthPanel from "../components/auth-panel";

export default function Home() {
  const githubUrl = "https://github.com/windbug99/metel";
  const signInButtonClassName =
    "rounded-md border border-border bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-sm transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background";
  const githubButtonClassName =
    "rounded-md border border-border bg-card px-5 py-2.5 text-sm font-medium text-foreground transition hover:bg-accent hover:text-accent-foreground";
  const services = [
    { name: "Notion", icon: "/logos/notion.svg", status: "Connected" },
    { name: "Linear", icon: "/logos/linear.svg", status: "Connected" },
    { name: "Google Calendar", icon: "/logos/google.svg", status: "Connected" },
    { name: "Spotify", icon: "/logos/spotify.svg", status: "Limited" }
  ];
  const useCases = [
    "Fetch today's meetings from Google Calendar, create a Notion meeting note draft for each meeting, and register each one as a Linear issue.",
    "Find planning-related Linear issues, summarize them in three sentences, and create a new Notion page.",
    "Update a Linear issue description based on content from a Notion page."
  ];

  return (
    <main className="relative min-h-screen overflow-hidden bg-background text-foreground">
      <div className="relative mx-auto flex min-h-screen w-full max-w-[1080px] flex-col px-5 py-6 sm:px-8">
        <header className="flex items-center justify-between gap-3 border-b border-border py-4">
          <p className="font-mono text-xs uppercase tracking-[0.22em] text-muted-foreground">metel</p>
          <div className="flex items-center gap-2">
            <AuthPanel
              variant="button"
              signInLabel="Sign in"
              signInButtonClassName="rounded-md border border-border bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground transition hover:opacity-90"
            />
            <a
              href={githubUrl}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition hover:bg-accent hover:text-accent-foreground"
            >
              GitHub
            </a>
          </div>
        </header>

        <section className="py-14 sm:py-16 lg:py-20">
          <div className="mx-auto w-full max-w-3xl">
            <p className="font-mono text-xs uppercase tracking-[0.3em] text-muted-foreground">Operational Execution Layer</p>
            <h1 className="mt-5 text-[2rem] font-semibold leading-[1.03] tracking-tight text-foreground sm:text-[3.35rem] lg:text-[4.5rem]">
              From Prompt to
              <br />
              Verified Operations.
            </h1>
            <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-muted-foreground sm:text-[17px]">
              metel is an operational execution engine. It generates dynamic workflows, executes cross-service actions,
              and enforces verification with rollback-aware failure handling.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-2.5 sm:gap-3">
              <AuthPanel
                variant="button"
                signInLabel="Sign in"
                signInButtonClassName={signInButtonClassName}
              />
              <a
                href={githubUrl}
                target="_blank"
                rel="noreferrer"
                className={githubButtonClassName}
              >
                GitHub
              </a>
            </div>
          </div>
        </section>

        <section className="border-t border-border py-10 sm:py-12">
          <div className="mx-auto w-full max-w-3xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Why metel</p>
          <div className="mt-4 grid gap-3.5 md:grid-cols-3">
            <article className="rounded-xl border border-border bg-card p-5">
              <p className="text-base font-semibold text-foreground">LLM Security Risks, Operationally Controlled</p>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                OAuth scopes, allowlisted tools, schema validation, and guardrails reduce high-risk model actions.
              </p>
            </article>
            <article className="rounded-xl border border-border bg-card p-5">
              <p className="text-base font-semibold text-foreground">Multi-Service Compositions</p>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Execute connected workflows across Calendar, Notion, Linear, and Telegram as one operation.
              </p>
            </article>
            <article className="rounded-xl border border-border bg-card p-5">
              <p className="text-base font-semibold text-foreground">Dynamic Workflow Generation</p>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Convert one request into an executable flow, then verify results with deterministic orchestration.
              </p>
            </article>
          </div>
          </div>
        </section>

        <section className="border-t border-border py-10 sm:py-12">
          <div className="mx-auto w-full max-w-3xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Use Cases</p>
          <div className="mt-4 space-y-3">
            {useCases.map((useCase, index) => (
              <article key={useCase} className="rounded-xl border border-border bg-card p-4">
                <p className="font-mono text-[11px] text-muted-foreground">Example {index + 1}</p>
                <p className="mt-2 break-words text-[13px] leading-relaxed text-foreground sm:text-sm">{useCase}</p>
              </article>
            ))}
          </div>
          </div>
        </section>

        <section className="border-t border-border py-10 sm:py-12">
          <div className="mx-auto w-full max-w-3xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Connected Services</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {services.map((service) => (
              <article key={service.name} className="flex items-center justify-between rounded-xl border border-border bg-card p-3.5">
                <div className="flex items-center gap-2.5">
                  <span className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-muted">
                    <img src={service.icon} alt={service.name} width={18} height={18} className="h-[18px] w-[18px] object-contain" />
                  </span>
                  <p className="text-sm font-medium text-foreground">{service.name}</p>
                </div>
                <span className="rounded-full border border-border bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                  {service.status}
                </span>
              </article>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Setup section is intentionally omitted. metel does not provide a personal self-host install flow yet.
          </p>
          </div>
        </section>

        <section className="border-t border-border py-10 sm:py-12">
          <div className="mx-auto w-full max-w-3xl">
          <div className="max-w-3xl rounded-2xl border border-border bg-card p-6">
            <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Security & Reliability</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-foreground">LLM Security Is an Execution Problem</h2>
            <ul className="mt-4 space-y-2 text-sm leading-relaxed text-muted-foreground">
              <li>- Schema-validated payloads and slot checks before tool calls</li>
              <li>- Budget limits, duplicate prevention, and fallback control</li>
              <li>- Rollback-aware failure handling for multi-step workflows</li>
              <li>- Structured traces for post-run verification and audit</li>
            </ul>
          </div>
          </div>
        </section>

        <footer className="border-t border-border py-8">
          <div className="flex flex-wrap items-center gap-3">
            <AuthPanel
              variant="button"
              signInLabel="Sign in"
              signInButtonClassName={signInButtonClassName}
            />
            <a
              href={githubUrl}
              target="_blank"
              rel="noreferrer"
              className={githubButtonClassName}
            >
              GitHub
            </a>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">Track every execution with structured logs.</p>
        </footer>
      </div>
    </main>
  );
}
