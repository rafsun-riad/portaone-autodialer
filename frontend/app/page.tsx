import { redirect } from "next/navigation";

import { LoginScreen } from "@/components/auth/login-screen";
import { getStoredSession } from "@/lib/session";

export default async function Home() {
  const session = await getStoredSession();

  if (session.accessToken && session.username) {
    redirect("/dashboard");
  }

  return (
    <main className="relative isolate min-h-screen overflow-hidden px-6 py-10 sm:px-10 lg:px-16">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(15,118,110,0.18),_transparent_35%),radial-gradient(circle_at_bottom_right,_rgba(217,119,6,0.18),_transparent_28%),linear-gradient(180deg,_rgba(255,255,255,0.82),_rgba(244,247,244,0.98))]" />
      <div className="relative mx-auto grid min-h-[calc(100vh-5rem)] max-w-7xl gap-10 lg:grid-cols-[1.15fr_0.85fr] lg:items-center">
        <section className="space-y-8 rounded-[2rem] border border-white/70 bg-white/65 p-8 shadow-[0_28px_90px_rgba(15,23,42,0.08)] backdrop-blur-xl lg:p-12">
          <div className="inline-flex items-center gap-3 rounded-full border border-teal-200/70 bg-teal-50/90 px-4 py-2 text-sm font-medium text-teal-900">
            PortaOne campaign operations
          </div>
          <div className="space-y-5">
            <h1 className="max-w-3xl text-4xl font-semibold leading-tight text-slate-950 sm:text-5xl lg:text-6xl">
              Launch voice campaigns with a cleaner control room and a stable
              calling pipeline.
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-slate-600">
              Authenticate against the existing PortaOne system, sync customer
              identity into your local platform, manage campaigns and contacts,
              and keep playback-ready voice assets tied to each campaign.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-3xl border border-slate-200/80 bg-slate-50/85 p-5">
              <p className="text-sm font-medium uppercase tracking-[0.18em] text-slate-500">
                Identity sync
              </p>
              <p className="mt-3 text-sm leading-7 text-slate-600">
                Customer records are refreshed on login and protected page
                loads.
              </p>
            </div>
            <div className="rounded-3xl border border-slate-200/80 bg-slate-50/85 p-5">
              <p className="text-sm font-medium uppercase tracking-[0.18em] text-slate-500">
                Campaign pace
              </p>
              <p className="mt-3 text-sm leading-7 text-slate-600">
                Operators can schedule, pause, resume, and restart outbound
                campaigns.
              </p>
            </div>
            <div className="rounded-3xl border border-slate-200/80 bg-slate-50/85 p-5">
              <p className="text-sm font-medium uppercase tracking-[0.18em] text-slate-500">
                Voice playback
              </p>
              <p className="mt-3 text-sm leading-7 text-slate-600">
                Audio files remain attached to campaigns and can be previewed
                before calls go out.
              </p>
            </div>
          </div>
        </section>
        <LoginScreen />
      </div>
    </main>
  );
}
