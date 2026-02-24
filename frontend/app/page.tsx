import AuthPanel from "../components/auth-panel";

export default function Home() {
  const githubUrl = "https://github.com/windbug99/metel";
  const signInButtonClassName =
    "rounded-md border border-[#d7dbe4] bg-[#F7F8FA] px-5 py-2.5 text-sm font-semibold text-[#0b1320] shadow-[0_0_0_1px_rgba(247,248,250,0.35),0_8px_26px_rgba(18,24,34,0.35)] transition hover:bg-[#e9ecf1] hover:shadow-[0_0_0_1px_rgba(233,236,241,0.45),0_10px_30px_rgba(18,24,34,0.42)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F7F8FA] focus-visible:ring-offset-2 focus-visible:ring-offset-[#050506]";
  const githubButtonClassName =
    "rounded-md border border-[#303038] bg-[#121217] px-5 py-2.5 text-sm font-medium text-[#f0f0f0] transition hover:border-[#4a4a56] hover:bg-[#16161d]";
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
    <main className="relative min-h-screen overflow-hidden bg-[#050506] text-[#f5f5f5]">
      <div className="pointer-events-none absolute inset-0 opacity-70">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#1a1a1c_1px,transparent_1px),linear-gradient(to_bottom,#1a1a1c_1px,transparent_1px)] bg-[size:56px_56px]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_12%,#1d2430_0px,transparent_380px),radial-gradient(circle_at_84%_8%,#2a1f2a_0px,transparent_340px),radial-gradient(circle_at_50%_82%,#122025_0px,transparent_420px)]" />
      </div>

      <div className="relative mx-auto flex min-h-screen w-full max-w-[1080px] flex-col px-5 py-6 sm:px-8">
        <header className="flex items-center justify-between gap-3 border-b border-[#212125] py-4">
          <p className="font-mono text-xs uppercase tracking-[0.22em] text-[#9ba0aa]">metel</p>
          <div className="flex items-center gap-2">
            <AuthPanel
              variant="button"
              signInLabel="Sign in"
              signInButtonClassName="rounded-md border border-[#d7dbe4] bg-[#F7F8FA] px-3 py-1.5 text-sm font-semibold text-[#0b1320] transition hover:bg-[#e9ecf1]"
            />
            <a
              href={githubUrl}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-[#303038] bg-[#121217] px-3 py-1.5 text-sm font-medium text-[#f0f0f0] transition hover:border-[#4a4a56]"
            >
              GitHub
            </a>
          </div>
        </header>

        <section className="py-14 sm:py-16 lg:py-20">
          <div className="mx-auto w-full max-w-3xl">
            <p className="font-mono text-xs uppercase tracking-[0.3em] text-[#aab2bf] [text-shadow:0_0_16px_rgba(173,184,201,0.45)]">Operational Execution Layer</p>
            <h1 className="mt-5 text-[2rem] font-semibold leading-[1.03] tracking-tight text-[#f7f8fa] sm:text-[3.35rem] lg:text-[4.5rem]">
              From Prompt to
              <br />
              Verified Operations.
            </h1>
            <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-[#b8becc] sm:text-[17px]">
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

        <section className="border-t border-[#212125] py-10 sm:py-12">
          <div className="mx-auto w-full max-w-3xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-[#a9b1be] [text-shadow:0_0_14px_rgba(173,184,201,0.42)]">Why metel</p>
          <div className="mt-4 grid gap-3.5 md:grid-cols-3">
            <article className="rounded-xl border border-[#282831] bg-[#111116] p-5">
              <p className="text-base font-semibold text-[#f3f4f7]">LLM Security Risks, Operationally Controlled</p>
              <p className="mt-2 text-sm leading-relaxed text-[#a8adb9]">
                OAuth scopes, allowlisted tools, schema validation, and guardrails reduce high-risk model actions.
              </p>
            </article>
            <article className="rounded-xl border border-[#282831] bg-[#111116] p-5">
              <p className="text-base font-semibold text-[#f3f4f7]">Multi-Service Compositions</p>
              <p className="mt-2 text-sm leading-relaxed text-[#a8adb9]">
                Execute connected workflows across Calendar, Notion, Linear, and Telegram as one operation.
              </p>
            </article>
            <article className="rounded-xl border border-[#282831] bg-[#111116] p-5">
              <p className="text-base font-semibold text-[#f3f4f7]">Dynamic Workflow Generation</p>
              <p className="mt-2 text-sm leading-relaxed text-[#a8adb9]">
                Convert one request into an executable flow, then verify results with deterministic orchestration.
              </p>
            </article>
          </div>
          </div>
        </section>

        <section className="border-t border-[#212125] py-10 sm:py-12">
          <div className="mx-auto w-full max-w-3xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-[#a9b1be] [text-shadow:0_0_14px_rgba(173,184,201,0.42)]">Use Cases</p>
          <div className="mt-4 space-y-3">
            {useCases.map((useCase, index) => (
              <article key={useCase} className="rounded-xl border border-[#282831] bg-[#111116] p-4">
                <p className="font-mono text-[11px] text-[#9ca3af]">Example {index + 1}</p>
                <p className="mt-2 break-words text-[13px] leading-relaxed text-[#dde1e9] sm:text-sm">{useCase}</p>
              </article>
            ))}
          </div>
          </div>
        </section>

        <section className="border-t border-[#212125] py-10 sm:py-12">
          <div className="mx-auto w-full max-w-3xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-[#a9b1be] [text-shadow:0_0_14px_rgba(173,184,201,0.42)]">Connected Services</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {services.map((service) => (
              <article key={service.name} className="flex items-center justify-between rounded-xl border border-[#282831] bg-[#111116] p-3.5">
                <div className="flex items-center gap-2.5">
                  <span className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[#30303a] bg-[#17171d]">
                    <img src={service.icon} alt={service.name} width={18} height={18} className="h-[18px] w-[18px] object-contain" />
                  </span>
                  <p className="text-sm font-medium text-[#edf0f5]">{service.name}</p>
                </div>
                <span className="rounded-full border border-[#3a3a45] bg-[#17171e] px-2 py-0.5 text-[11px] text-[#b8bec9]">
                  {service.status}
                </span>
              </article>
            ))}
          </div>
          <p className="mt-3 text-xs text-[#8f95a3]">
            Setup section is intentionally omitted. metel does not provide a personal self-host install flow yet.
          </p>
          </div>
        </section>

        <section className="border-t border-[#212125] py-10 sm:py-12">
          <div className="mx-auto w-full max-w-3xl">
          <div className="max-w-3xl rounded-2xl border border-[#2b2b34] bg-[#111116] p-6">
            <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-[#a9b1be] [text-shadow:0_0_14px_rgba(173,184,201,0.42)]">Security & Reliability</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-[#f0f3f8]">LLM Security Is an Execution Problem</h2>
            <ul className="mt-4 space-y-2 text-sm leading-relaxed text-[#b0b6c2]">
              <li>- Schema-validated payloads and slot checks before tool calls</li>
              <li>- Budget limits, duplicate prevention, and fallback control</li>
              <li>- Rollback-aware failure handling for multi-step workflows</li>
              <li>- Structured traces for post-run verification and audit</li>
            </ul>
          </div>
          </div>
        </section>

        <footer className="border-t border-[#212125] py-8">
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
          <p className="mt-3 text-xs text-[#8f95a3]">Track every execution with structured logs.</p>
        </footer>
      </div>
    </main>
  );
}
