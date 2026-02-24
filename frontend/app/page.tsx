import AuthPanel from "../components/auth-panel";

export default function Home() {
  const githubUrl = process.env.NEXT_PUBLIC_GITHUB_URL || "https://github.com";
  const services = [
    { name: "Notion", icon: "/logos/notion.svg", status: "Connected" },
    { name: "Linear", icon: "/logos/linear.svg", status: "Connected" },
    { name: "Google Calendar", icon: "/logos/google.svg", status: "Connected" },
    { name: "Telegram", icon: "/logos/telegram.svg", status: "Connected" },
    { name: "Spotify", icon: "/logos/spotify.svg", status: "Limited" }
  ];
  const useCases = [
    "Fetch today's meetings from Google Calendar, create a Notion meeting note draft for each meeting, and register each one as a Linear issue.",
    "Find planning-related Linear issues, summarize them in three sentences, and create a new Notion page.",
    "Update a Linear issue description based on content from a Notion page."
  ];

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#fbfbf9] text-[#111111]">
      <div className="pointer-events-none absolute inset-0 opacity-60">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ececec_1px,transparent_1px),linear-gradient(to_bottom,#ececec_1px,transparent_1px)] bg-[size:56px_56px]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,#f2f2f2_0px,transparent_420px),radial-gradient(circle_at_85%_15%,#f5f5f5_0px,transparent_360px)]" />
      </div>

      <div className="relative mx-auto flex min-h-screen w-full max-w-5xl flex-col px-5 py-6 sm:px-8">
        <header className="flex items-center justify-between gap-3 border-b border-[#e6e6e6] py-4">
          <p className="font-mono text-xs uppercase tracking-[0.22em] text-[#666]">metel</p>
          <a
            href={githubUrl}
            target="_blank"
            rel="noreferrer"
            className="rounded-md border border-[#d7d7d7] bg-white px-3 py-1.5 text-sm font-medium text-[#1a1a1a] transition hover:border-[#bdbdbd]"
          >
            GitHub
          </a>
        </header>

        <section className="py-14 sm:py-18 lg:py-20">
          <div className="mx-auto w-full max-w-4xl">
            <p className="font-mono text-xs uppercase tracking-[0.3em] text-[#6b6b6b]">Operational Execution Layer</p>
            <h1 className="mt-5 text-[2.12rem] font-semibold leading-[1.03] tracking-tight text-[#0c0c0c] sm:text-6xl lg:text-7xl">
              From Prompt to
              <br />
              Verified Operations.
            </h1>
            <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-[#3f3f3f] sm:text-lg">
              metel is an operational execution engine. It generates dynamic workflows, executes cross-service actions,
              and enforces verification with rollback-aware failure handling.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-2.5 sm:gap-3">
              <AuthPanel
                variant="button"
                signInLabel="Sign in"
                signInButtonClassName="rounded-md border border-[#121212] bg-[#121212] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#242424]"
              />
              <a
                href={githubUrl}
                target="_blank"
                rel="noreferrer"
                className="rounded-md border border-[#d7d7d7] bg-white px-5 py-2.5 text-sm font-medium text-[#1a1a1a] transition hover:border-[#bdbdbd]"
              >
                GitHub
              </a>
            </div>
          </div>
        </section>

        <section className="border-t border-[#e6e6e6] py-10 sm:py-12">
          <div className="mx-auto w-full max-w-4xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[#666]">Why metel</p>
          <div className="mt-4 grid gap-3.5 md:grid-cols-3">
            <article className="rounded-xl border border-[#e3e3e3] bg-white p-5">
              <p className="text-base font-semibold text-[#111]">LLM Security Risks, Operationally Controlled</p>
              <p className="mt-2 text-sm leading-relaxed text-[#4b4b4b]">
                OAuth scopes, allowlisted tools, schema validation, and guardrails reduce high-risk model actions.
              </p>
            </article>
            <article className="rounded-xl border border-[#e3e3e3] bg-white p-5">
              <p className="text-base font-semibold text-[#111]">Multi-Service Compositions</p>
              <p className="mt-2 text-sm leading-relaxed text-[#4b4b4b]">
                Execute connected workflows across Calendar, Notion, Linear, and Telegram as one operation.
              </p>
            </article>
            <article className="rounded-xl border border-[#e3e3e3] bg-white p-5">
              <p className="text-base font-semibold text-[#111]">Dynamic Workflow Generation</p>
              <p className="mt-2 text-sm leading-relaxed text-[#4b4b4b]">
                Convert one request into an executable flow, then verify results with deterministic orchestration.
              </p>
            </article>
          </div>
          </div>
        </section>

        <section className="border-t border-[#e6e6e6] py-10 sm:py-12">
          <div className="mx-auto w-full max-w-4xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[#666]">Use Cases</p>
          <div className="mt-4 space-y-3">
            {useCases.map((useCase, index) => (
              <article key={useCase} className="rounded-xl border border-[#e3e3e3] bg-white p-4">
                <p className="font-mono text-[11px] text-[#666]">Example {index + 1}</p>
                <p className="mt-2 break-words text-[13px] leading-relaxed text-[#202020] sm:text-sm">{useCase}</p>
              </article>
            ))}
          </div>
          </div>
        </section>

        <section className="border-t border-[#e6e6e6] py-10 sm:py-12">
          <div className="mx-auto w-full max-w-4xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[#666]">Connected Services</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {services.map((service) => (
              <article key={service.name} className="flex items-center justify-between rounded-xl border border-[#e3e3e3] bg-white p-3.5">
                <div className="flex items-center gap-2.5">
                  <img src={service.icon} alt={service.name} width={18} height={18} className="h-[18px] w-[18px] object-contain" />
                  <p className="text-sm font-medium text-[#171717]">{service.name}</p>
                </div>
                <span className="rounded-full border border-[#d9d9d9] bg-[#fafafa] px-2 py-0.5 text-[11px] text-[#555]">
                  {service.status}
                </span>
              </article>
            ))}
          </div>
          <p className="mt-3 text-xs text-[#666]">
            Setup section is intentionally omitted. metel does not provide a personal self-host install flow yet.
          </p>
          </div>
        </section>

        <section className="border-t border-[#e6e6e6] py-10 sm:py-12">
          <div className="mx-auto w-full max-w-4xl">
          <div className="max-w-4xl rounded-2xl border border-[#dddddd] bg-white p-6">
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[#666]">Security & Reliability</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-[#101010]">LLM Security Is an Execution Problem</h2>
            <ul className="mt-4 space-y-2 text-sm leading-relaxed text-[#3f3f3f]">
              <li>- Schema-validated payloads and slot checks before tool calls</li>
              <li>- Budget limits, duplicate prevention, and fallback control</li>
              <li>- Rollback-aware failure handling for multi-step workflows</li>
              <li>- Structured traces for post-run verification and audit</li>
            </ul>
          </div>
          </div>
        </section>

        <footer className="border-t border-[#e6e6e6] py-8">
          <div className="flex flex-wrap items-center gap-3">
            <AuthPanel
              variant="button"
              signInLabel="Sign in"
              signInButtonClassName="rounded-md border border-[#121212] bg-[#121212] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#242424]"
            />
            <a
              href={githubUrl}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-[#d7d7d7] bg-white px-5 py-2.5 text-sm font-medium text-[#1a1a1a] transition hover:border-[#bdbdbd]"
            >
              GitHub
            </a>
          </div>
          <p className="mt-3 text-xs text-[#666]">Track every execution with structured logs.</p>
        </footer>
      </div>
    </main>
  );
}
