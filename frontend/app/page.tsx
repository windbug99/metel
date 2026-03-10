import AuthPanel from "../components/auth-panel";

export default function Home() {
  const githubUrl = "https://github.com/windbug99/metel";
  const signInButtonClassName =
    "rounded-md border border-border bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-sm transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background";
  const githubButtonClassName =
    "rounded-md border border-border bg-card px-5 py-2.5 text-sm font-medium text-foreground transition hover:bg-accent hover:text-accent-foreground";

  const services = [
    { name: "Notion", icon: "/logos/notion.svg", count: "30 Tools", status: "Connected" },
    { name: "Linear", icon: "/logos/linear.svg", count: "8 Tools", status: "Connected" },
    { name: "GitHub", icon: "/logos/github.svg", count: "5 Tools", status: "Connected" }
  ];

  const controlLayers = [
    { name: "Auth", detail: "API key validation with scoped tool permissions" },
    { name: "Schema", detail: "JSON Schema check on every tool input" },
    { name: "Policy", detail: "Allow/deny rules by key, team, and tool" },
    { name: "Risk Gate", detail: "Blocks destructive ops (delete, archive) by default" },
    { name: "Resolver", detail: "Converts human-readable names to system IDs" },
    { name: "Retry & Quota", detail: "Per-key rate limits with backoff and alerting" },
    { name: "Audit", detail: "Every call logged with actor, decision, and latency" },
    { name: "RBAC", detail: "Role-based visibility: Owner, Admin, Member" }
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

        {/* Section 1: Hero */}
        <section className="py-14 sm:py-16 lg:py-20">
          <div className="mx-auto w-full max-w-3xl text-center sm:text-left">
            <p className="font-mono text-xs uppercase tracking-[0.3em] text-muted-foreground">AI Action Control Platform</p>
            <h1 className="mt-5 text-[2.5rem] font-semibold leading-[1.03] tracking-tight text-foreground sm:text-[3.35rem] lg:text-[4.5rem]">
              Deploy AI Agents with
              <br />
              Absolute Control.
            </h1>
            <p className="mt-6 max-w-2xl text-[16px] leading-relaxed text-muted-foreground sm:text-[18px]">
              The execution control layer for your AI workforce. Enforce policies,
              audit every action, and mitigate risks across Notion, Linear, and GitHub.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-2.5 sm:justify-start sm:gap-3">
              <AuthPanel
                variant="button"
                signInLabel="Get Started Free"
                signInButtonClassName={signInButtonClassName}
              />
              <a
                href="https://github.com/windbug99/metel#quick-start"
                target="_blank"
                rel="noreferrer"
                className={githubButtonClassName}
              >
                View Docs
              </a>
            </div>
          </div>
        </section>

        {/* Section 2: The Core Problem */}
        <section className="border-t border-border py-12 sm:py-16">
          <div className="mx-auto w-full max-w-3xl text-center sm:text-left">
            <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Safety First</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">Scaling AI shouldn't be a security risk.</h2>
            <div className="mt-8 grid gap-4 md:grid-cols-3">
              <article className="rounded-xl border border-border bg-card p-6">
                <p className="text-base font-semibold text-foreground">Uncontrolled Mutations</p>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground italic">
                  "I didn't mean to delete that database..."
                </p>
                <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
                  Prevent accidental data loss by blocking destructive model-generated actions.
                </p>
              </article>
              <article className="rounded-xl border border-border bg-card p-6">
                <p className="text-base font-semibold text-foreground">Privilege Chaos</p>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground italic">
                  "Who authorized this agent to post?"
                </p>
                <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
                  Enforce least-privilege policies across all your connected SaaS workspaces.
                </p>
              </article>
              <article className="rounded-xl border border-border bg-card p-6">
                <p className="text-base font-semibold text-foreground">The Audit Gap</p>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground italic">
                  "What did the agents do at 3 AM?"
                </p>
                <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
                  Unified operational logs of every tool call, decision, and execution result.
                </p>
              </article>
            </div>
          </div>
        </section>

        {/* Section 3: The 8-Layer Solution */}
        <section className="border-t border-border py-12 sm:py-16">
          <div className="mx-auto w-full max-w-3xl">
            <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">The Control Layer</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">Safety at Every Step.</h2>
            <div className="mt-8 overflow-hidden rounded-2xl border border-border bg-card">
              <div className="grid grid-cols-1 divide-y divide-border sm:grid-cols-2 sm:divide-x sm:divide-y-0">
                <div className="divide-y divide-border">
                  {controlLayers.slice(0, 4).map((layer) => (
                    <div key={layer.name} className="p-4 sm:p-5">
                      <p className="text-sm font-bold text-foreground">/ {layer.name}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{layer.detail}</p>
                    </div>
                  ))}
                </div>
                <div className="divide-y divide-border">
                  {controlLayers.slice(4).map((layer) => (
                    <div key={layer.name} className="p-4 sm:p-5">
                      <p className="text-sm font-bold text-foreground">/ {layer.name}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{layer.detail}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Section 4: Integration Ecosystem */}
        <section className="border-t border-border py-12 sm:py-16">
          <div className="mx-auto w-full max-w-3xl">
            <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Ecosystem</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">One Gateway. 40+ Tools.</h2>
            <div className="mt-8 grid gap-4 sm:grid-cols-3">
              {services.map((service) => (
                <article key={service.name} className="group relative rounded-xl border border-border bg-card p-5 transition hover:bg-accent/5">
                  <div className="flex items-center gap-3">
                    <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-muted">
                      <img src={service.icon} alt={service.name} width={24} height={24} className="h-6 w-6 object-contain" />
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-foreground">{service.name}</p>
                      <p className="text-[11px] text-muted-foreground">{service.count}</p>
                    </div>
                  </div>
                  <div className="mt-4 flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                    <span className="text-[11px] font-medium text-muted-foreground">{service.status}</span>
                  </div>
                </article>
              ))}
            </div>
            <p className="mt-6 text-center text-xs text-muted-foreground">
              Built on the Model Context Protocol (MCP) for seamless agent integration.
            </p>
          </div>
        </section>

        {/* Section 5: Developer Experience */}
        <section className="border-t border-border py-12 sm:py-16">
          <div className="mx-auto w-full max-w-3xl">
            <div className="rounded-2xl border border-border bg-card p-6 sm:p-8">
              <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Developer Experience</p>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight text-foreground">Built by developers, for developers.</h2>
              <ul className="mt-6 grid gap-4 text-sm sm:grid-cols-2">
                <li className="flex gap-3 text-muted-foreground">
                  <span className="text-foreground">01</span>
                  <span><strong>MCP Native</strong> — Standardized bridge between LLMs and real-world tools.</span>
                </li>
                <li className="flex gap-3 text-muted-foreground">
                  <span className="text-foreground">02</span>
                  <span><strong>Claude Desktop Ready</strong> — Copy-paste config to start in seconds.</span>
                </li>
                <li className="flex gap-3 text-muted-foreground">
                  <span className="text-foreground">03</span>
                  <span><strong>Vercel-Inspired UI</strong> — Modern dashboard for clear operational oversight.</span>
                </li>
                <li className="flex gap-3 text-muted-foreground">
                  <span className="text-foreground">04</span>
                  <span><strong>API First</strong> — Secure, RESTful management of keys and policies.</span>
                </li>
              </ul>
            </div>
          </div>
        </section>

        <footer className="border-t border-border py-12">
          <div className="mx-auto w-full max-w-3xl flex flex-col items-center gap-6 sm:flex-row sm:justify-between">
            <div className="flex flex-wrap items-center justify-center gap-3 sm:justify-start">
              <AuthPanel
                variant="button"
                signInLabel="Get Started Now"
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
            <p className="text-xs text-muted-foreground">Govern your AI workforce with structured audits.</p>
          </div>
        </footer>
      </div>
    </main>
  );
}
