import AuthPanel from "../components/auth-panel";

export default function Home() {
  const matrixRows = [
    "<> [] // || ++ -- :: .. ## ## ++ ||",
    "01 10 01 11 00 10 11 00 01 10 11 01",
    "{} <> [] () // \\\\ || :: == ++ -- ##",
    "11001010 01101001 10110010 01001101",
    "[] <> {} // || :: ++ -- __ .. ## ##",
    "0011 1100 1010 0101 1110 0001 0111"
  ];

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#f2f2f2] text-neutral-900">
      <div className="pointer-events-none absolute inset-0 opacity-60">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#e5e5e5_1px,transparent_1px),linear-gradient(to_bottom,#e5e5e5_1px,transparent_1px)] bg-[size:48px_48px]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,#d9d9d9_0px,transparent_420px),radial-gradient(circle_at_80%_70%,#dfdfdf_0px,transparent_460px)]" />
        <pre className="absolute -left-20 top-8 rotate-[-8deg] text-[10px] leading-4 text-neutral-500/50 sm:text-xs">
          {matrixRows.join("\n")}
        </pre>
        <pre className="absolute -right-24 bottom-10 rotate-[7deg] text-[10px] leading-4 text-neutral-600/40 sm:text-xs">
          {matrixRows.slice().reverse().join("\n")}
        </pre>
      </div>

      <div className="relative mx-auto flex min-h-screen w-full max-w-6xl flex-col px-6 py-8 sm:px-10 sm:py-12">
        <header className="flex items-center justify-between border-b border-neutral-300/80 pb-4">
          <p className="font-mono text-xs uppercase tracking-[0.28em] text-neutral-500">Autonomous API Router</p>
          <p className="font-mono text-xs text-neutral-500">v0.1</p>
        </header>

        <section className="grid flex-1 gap-8 py-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
          <div>
            <h1 className="text-5xl font-semibold tracking-tight text-black sm:text-6xl">Metel</h1>
            <p className="mt-4 max-w-xl text-base text-neutral-700 sm:text-lg">
              One assistant layer for your connected tools. Ask once, run across services.
            </p>

            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              <article className="rounded-xl border border-neutral-300 bg-white/70 p-4 backdrop-blur">
                <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-neutral-500">01</p>
                <p className="mt-2 text-sm font-medium text-neutral-900">Unified Commands</p>
                <p className="mt-1 text-xs text-neutral-600">Single request flow for connected APIs.</p>
              </article>
              <article className="rounded-xl border border-neutral-300 bg-white/70 p-4 backdrop-blur">
                <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-neutral-500">02</p>
                <p className="mt-2 text-sm font-medium text-neutral-900">Autonomous Steps</p>
                <p className="mt-1 text-xs text-neutral-600">Plans and executes tool chains automatically.</p>
              </article>
              <article className="rounded-xl border border-neutral-300 bg-white/70 p-4 backdrop-blur">
                <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-neutral-500">03</p>
                <p className="mt-2 text-sm font-medium text-neutral-900">Traceable Logs</p>
                <p className="mt-1 text-xs text-neutral-600">Review each execution and fallback reason.</p>
              </article>
            </div>

            <div className="mt-8 rounded-2xl border border-neutral-300 bg-white/75 p-4 backdrop-blur">
              <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-neutral-500">
                Connectable Services
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {["Notion", "Linear", "Telegram", "Spotify (Disabled)", "Slack (Disabled)"].map((service) => (
                  <span
                    key={service}
                    className="rounded-full border border-neutral-300 bg-neutral-100 px-3 py-1 text-xs font-medium text-neutral-700"
                  >
                    {service}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-neutral-300 bg-white/85 p-6 shadow-[0_12px_40px_rgba(10,10,10,0.08)] backdrop-blur-sm">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-neutral-500">Get Started</p>
            <h2 className="mt-2 text-2xl font-semibold text-black">Sign in to your workspace</h2>
            <p className="mt-2 text-sm text-neutral-600">
              Login is required to open the dashboard and connect external APIs.
            </p>
            <AuthPanel
              className="mt-5 rounded-xl border border-neutral-300 bg-neutral-50 p-5"
              signInButtonClassName="rounded-md border border-neutral-900 bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-neutral-800"
            />
          </div>
        </section>
      </div>
    </main>
  );
}
