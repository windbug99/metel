import AuthPanel from "../components/auth-panel";

export default function Home() {
  const services = ["Notion", "Linear", "Telegram", "Spotify (Disabled)", "Slack (Disabled)"];

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#F4F2F4] text-[#222326]">
      <div className="pointer-events-none absolute inset-0 opacity-60">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#e5e5e5_1px,transparent_1px),linear-gradient(to_bottom,#e5e5e5_1px,transparent_1px)] bg-[size:48px_48px]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,#d9d9d9_0px,transparent_420px),radial-gradient(circle_at_80%_70%,#dfdfdf_0px,transparent_460px)]" />
      </div>

      <div className="relative mx-auto flex min-h-screen w-full max-w-7xl flex-col px-5 py-6 sm:px-8">
        <section className="flex flex-1 flex-col py-20 sm:py-24">
          <div className="mx-auto w-full max-w-4xl text-center">
            <p className="font-mono text-xs uppercase tracking-[0.3em] text-neutral-500">Autonomous API Router</p>
            <h1 className="mt-6 text-6xl font-semibold tracking-tight text-black sm:text-7xl lg:text-8xl">
              Connect your tools.
              <br />
              Automate with one command.
            </h1>
            <p className="mx-auto mt-7 max-w-2xl text-lg text-neutral-700 sm:text-xl">
              Metel routes one request across connected services and returns traceable execution results.
            </p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
              <AuthPanel
                variant="button"
                signInButtonClassName="rounded-md border border-neutral-900 bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-neutral-800"
              />
            </div>
            <div className="mt-10 flex flex-wrap items-center justify-center gap-2">
              {services.map((service) => (
                <span
                  key={service}
                  className="rounded-full border border-neutral-300 bg-white/85 px-3 py-1 text-xs font-medium text-neutral-700"
                >
                  {service}
                </span>
              ))}
            </div>
          </div>

          <div id="overview" className="mx-auto mt-16 grid w-full max-w-6xl gap-4 md:grid-cols-3">
            <article className="rounded-xl border border-neutral-300 bg-white/80 p-5 backdrop-blur">
              <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-neutral-500">01</p>
              <p className="mt-2 text-base font-medium text-neutral-900">Unified Commands</p>
              <p className="mt-2 text-sm text-neutral-600">
                Ask once and run across tools without manual API switching.
              </p>
            </article>
            <article className="rounded-xl border border-neutral-300 bg-white/80 p-5 backdrop-blur">
              <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-neutral-500">02</p>
              <p className="mt-2 text-base font-medium text-neutral-900">Autonomous Workflows</p>
              <p className="mt-2 text-sm text-neutral-600">
                Plan, call tools, and recover with fallback logic automatically.
              </p>
            </article>
            <article className="rounded-xl border border-neutral-300 bg-white/80 p-5 backdrop-blur">
              <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-neutral-500">03</p>
              <p className="mt-2 text-base font-medium text-neutral-900">Execution Trace</p>
              <p className="mt-2 text-sm text-neutral-600">
                Inspect every step, status, and reason from dashboard logs.
              </p>
            </article>
          </div>

          <div className="mx-auto mt-4 w-full max-w-6xl rounded-2xl border border-neutral-300 bg-white/80 p-5 backdrop-blur">
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-neutral-500">Service Banner</p>
            <p className="mt-2 text-sm text-neutral-700">
              Start with Notion, Linear, and Telegram. More services can be added as API availability changes.
            </p>
          </div>
        </section>
        
        <footer className="border-t border-neutral-300/80 py-4">
          <p className="text-xs text-neutral-500">Metel prototype</p>
        </footer>
      </div>
    </main>
  );
}
