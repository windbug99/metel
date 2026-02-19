import AuthPanel from "../components/auth-panel";

export default function Home() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-4xl font-bold">metel</h1>
      <p className="mt-4 text-lg text-gray-700">
        AI assistant prototype that understands all your services
      </p>
      <AuthPanel />
    </main>
  );
}
