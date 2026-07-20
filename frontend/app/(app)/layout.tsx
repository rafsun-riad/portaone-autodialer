import { PhoneCall, Wallet } from "lucide-react";
import { redirect } from "next/navigation";

import { SidebarNav } from "@/components/app/sidebar-nav";
import { LogoutButton } from "@/components/auth/logout-button";
import { SessionBootstrap } from "@/components/session-bootstrap";
import { fetchBackendJson } from "@/lib/server-api";
import { getStoredSession } from "@/lib/session";
import { type SessionUser } from "@/stores/app-store";

const navigation: Array<{
  href: string;
  label: string;
  icon: "dashboard" | "campaigns" | "contacts" | "audio";
}> = [
  { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { href: "/campaigns", label: "Campaigns", icon: "campaigns" },
  { href: "/contacts", label: "Contacts", icon: "contacts" },
  { href: "/audio", label: "Campaign Audio", icon: "audio" },
];

type MeResponse = {
  username: string;
  i_customer: number | null;
  last_synced_at: string | null;
  external_data: {
    firstname?: string;
    lastname?: string;
    balance?: number;
    name?: string;
  };
};

export default async function AppLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const session = await getStoredSession();
  if (!session.accessToken || !session.username) {
    redirect("/");
  }

  let profile: MeResponse;
  try {
    profile = await fetchBackendJson<MeResponse>("auth/me/");
  } catch {
    redirect("/");
  }

  const user: SessionUser = {
    username: profile.username,
    iCustomer: profile.i_customer,
    displayName:
      [profile.external_data.firstname, profile.external_data.lastname]
        .filter(Boolean)
        .join(" ") ||
      profile.external_data.name ||
      profile.username,
    balance:
      typeof profile.external_data.balance === "number"
        ? profile.external_data.balance
        : null,
    lastSyncedAt: profile.last_synced_at,
  };

  return (
    <div className="min-h-screen bg-[linear-gradient(180deg,rgba(236,240,247,0.95),rgba(246,248,252,1))] text-slate-900 lg:h-screen lg:overflow-hidden">
      <SessionBootstrap user={user} />
      <div className="flex min-h-screen lg:h-screen">
        <aside className="dashboard-sidebar hidden w-73 shrink-0 lg:fixed lg:inset-y-0 lg:left-0 lg:flex lg:h-screen lg:flex-col lg:px-7 lg:py-8">
          <div className="flex min-h-0 flex-1 flex-col">
            <div>
              <div className="flex items-center gap-3 text-white">
                <div className="flex size-10 items-center justify-center rounded-2xl border border-white/30 bg-white/10 backdrop-blur-sm">
                  <PhoneCall className="size-5" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-white/65">
                    PortaOne
                  </p>
                  <h2 className="mt-1 text-xl font-semibold">Autodialer</h2>
                </div>
              </div>
              <p className="mt-5 max-w-xs text-sm leading-7 text-white/72">
                Campaign control, customer sync, and playback-ready calling in
                one operator workspace.
              </p>
            </div>

            <div className="dashboard-sidebar-scroll mt-8 min-h-0 flex-1 pr-2">
              <SidebarNav items={navigation} />
            </div>

            <div className="space-y-4 rounded-[1.8rem] border border-white/20 bg-white/10 p-5 backdrop-blur-sm">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-white/60">
                  Signed in as
                </p>
                <h3 className="mt-2 text-lg font-semibold text-white">
                  {user.displayName}
                </h3>
                <p className="mt-1 text-sm text-white/72">{user.username}</p>
              </div>
              <div className="grid gap-2 text-sm text-white/78">
                <div className="flex items-center justify-between gap-4 rounded-2xl bg-white/8 px-3 py-2.5">
                  <span>Customer ID</span>
                  <span className="font-semibold text-white">
                    {user.iCustomer ?? "-"}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-4 rounded-2xl bg-white/8 px-3 py-2.5">
                  <span>Balance</span>
                  <span className="font-semibold text-white">
                    {typeof user.balance === "number"
                      ? user.balance.toFixed(2)
                      : "-"}
                  </span>
                </div>
              </div>
              <LogoutButton />
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col px-4 py-4 sm:px-6 lg:ml-73 lg:h-screen lg:overflow-y-auto lg:px-8">
          <header className="dashboard-topbar rounded-[2rem] px-5 py-4 sm:px-7">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="section-heading">Campaign workspace</p>
                <h1 className="mt-2 text-2xl font-semibold text-slate-950 sm:text-[2rem]">
                  Voice operations
                </h1>
                <p className="mt-1 text-sm text-slate-600">
                  Schedules stay in Bangladesh time and the right panel remains
                  dedicated to day-to-day operator work.
                </p>
              </div>
              <div className="flex items-center gap-3 self-start rounded-full border border-slate-200 bg-white px-3 py-2 shadow-[0_14px_35px_rgba(15,23,42,0.06)] md:self-auto">
                <div className="flex size-10 items-center justify-center rounded-full bg-[linear-gradient(135deg,#8b5cf6,#ec4899)] text-white">
                  <Wallet className="size-4" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-slate-400">
                    Active operator
                  </p>
                  <p className="text-sm font-semibold text-slate-900">
                    {user.displayName}
                  </p>
                </div>
              </div>
            </div>
          </header>

          <main className="mt-5 min-h-[calc(100vh-8.5rem)] rounded-[2rem] bg-transparent lg:pb-8">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
