import { fetchBackendJson } from "@/lib/server-api";
import { formatDhakaDateTime } from "@/lib/time";
import {
  Activity,
  ChartColumnBig,
  Clock3,
  MessageSquareMore,
  Radio,
  ShieldCheck,
} from "lucide-react";

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

export default async function DashboardPage() {
  const me = await fetchBackendJson<MeResponse>("auth/me/");
  const displayName =
    [me.external_data.firstname, me.external_data.lastname]
      .filter(Boolean)
      .join(" ") ||
    me.external_data.name ||
    me.username;

  return (
    <div className="space-y-5">
      <section className="grid gap-4 xl:grid-cols-[1.45fr_0.55fr]">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <div className="dashboard-stat-card">
            <div className="dashboard-stat-icon bg-[linear-gradient(135deg,#f97316,#fb7185)] text-white">
              <ShieldCheck className="size-4" />
            </div>
            <p className="mt-5 text-sm font-medium text-slate-500">
              Customer ID
            </p>
            <h2 className="mt-2 text-4xl font-semibold tracking-tight text-slate-950">
              {me.i_customer ?? "-"}
            </h2>
          </div>

          <div className="dashboard-stat-card">
            <div className="dashboard-stat-icon bg-[linear-gradient(135deg,#8b5cf6,#d946ef)] text-white">
              <Radio className="size-4" />
            </div>
            <p className="mt-5 text-sm font-medium text-slate-500">
              Active profile
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
              {displayName}
            </h2>
          </div>

          <div className="dashboard-stat-card">
            <div className="dashboard-stat-icon bg-[linear-gradient(135deg,#ec4899,#fb7185)] text-white">
              <ChartColumnBig className="size-4" />
            </div>
            <p className="mt-5 text-sm font-medium text-slate-500">Balance</p>
            <h2 className="mt-2 text-4xl font-semibold tracking-tight text-slate-950">
              {typeof me.external_data.balance === "number"
                ? me.external_data.balance.toFixed(2)
                : "-"}
            </h2>
          </div>

          <div className="dashboard-stat-card">
            <div className="dashboard-stat-icon bg-[linear-gradient(135deg,#4f46e5,#8b5cf6)] text-white">
              <Clock3 className="size-4" />
            </div>
            <p className="mt-5 text-sm font-medium text-slate-500">Last sync</p>
            <h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-950">
              {formatDhakaDateTime(me.last_synced_at)}
            </h2>
          </div>
        </div>

        <div className="dashboard-panel p-5">
          <p className="section-heading">Operator profile</p>
          <div className="mt-5 space-y-4 text-sm text-slate-600">
            <div className="flex items-center justify-between gap-4 rounded-2xl bg-slate-50 px-4 py-3">
              <span>Username</span>
              <span className="font-semibold text-slate-900">
                {me.username}
              </span>
            </div>
            <div className="flex items-center justify-between gap-4 rounded-2xl bg-slate-50 px-4 py-3">
              <span>Display name</span>
              <span className="font-semibold text-slate-900">
                {displayName}
              </span>
            </div>
            <div className="flex items-center justify-between gap-4 rounded-2xl bg-slate-50 px-4 py-3">
              <span>Timezone</span>
              <span className="font-semibold text-slate-900">Asia/Dhaka</span>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.4fr_0.6fr]">
        <div className="dashboard-panel overflow-hidden p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="section-heading">Overview</p>
              <h3 className="mt-2 text-2xl font-semibold text-slate-950">
                Campaign telemetry will live here next.
              </h3>
            </div>
            <div className="rounded-full bg-[linear-gradient(135deg,rgba(251,113,133,0.12),rgba(249,115,22,0.14))] px-4 py-2 text-sm font-medium text-rose-600">
              Placeholder analytics
            </div>
          </div>

          <div className="mt-6 rounded-[2rem] border border-slate-200 bg-[linear-gradient(180deg,#ffffff,#f7f8fc)] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.6)]">
            <div className="grid h-[290px] gap-4 rounded-[1.6rem] bg-[linear-gradient(180deg,rgba(244,247,252,0.6),rgba(255,255,255,0.96))] p-5">
              <div className="flex items-center justify-between">
                <p className="text-base font-semibold text-slate-700">
                  Live performance canvas
                </p>
                <div className="flex items-center gap-2 text-xs font-medium text-slate-400">
                  <Activity className="size-4" />
                  Awaiting campaign activity
                </div>
              </div>

              <div className="relative overflow-hidden rounded-[1.4rem] border border-slate-200 bg-white px-4 py-5">
                <div className="absolute inset-x-4 top-6 grid gap-8">
                  <div className="h-px bg-slate-200" />
                  <div className="h-px bg-slate-200" />
                  <div className="h-px bg-slate-200" />
                  <div className="h-px bg-slate-200" />
                </div>
                <svg
                  className="relative z-10 h-full w-full"
                  viewBox="0 0 700 240"
                  fill="none"
                  preserveAspectRatio="none"
                >
                  <defs>
                    <linearGradient id="dash-fill" x1="0" x2="1" y1="0" y2="1">
                      <stop offset="0%" stopColor="#f43f5e" />
                      <stop offset="100%" stopColor="#fb923c" />
                    </linearGradient>
                  </defs>
                  <path
                    d="M0 220C60 160 120 118 180 124C240 130 300 168 360 124C420 80 480 18 540 28C600 38 650 174 700 146V240H0Z"
                    fill="url(#dash-fill)"
                    fillOpacity="0.95"
                  />
                </svg>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-5">
          <div className="dashboard-panel p-5">
            <p className="section-heading">Most relevant right now</p>
            <div className="mt-4 space-y-3">
              <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                Profile sync is now connected to the external system.
              </div>
              <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                Campaign execution controls are wired and ready for live data.
              </div>
              <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                Audio playback callbacks are already being persisted for
                inquiry.
              </div>
            </div>
          </div>

          <div className="dashboard-panel p-5">
            <p className="section-heading">Next build slices</p>
            <div className="mt-4 space-y-4 text-sm leading-7 text-slate-600">
              <div className="flex items-start gap-3 rounded-2xl bg-slate-50 px-4 py-3">
                <MessageSquareMore className="mt-0.5 size-4 text-violet-500" />
                <span>Campaign status distribution and overdue warnings.</span>
              </div>
              <div className="flex items-start gap-3 rounded-2xl bg-slate-50 px-4 py-3">
                <MessageSquareMore className="mt-0.5 size-4 text-pink-500" />
                <span>
                  Live counters for queued, connected, and terminated calls.
                </span>
              </div>
              <div className="flex items-start gap-3 rounded-2xl bg-slate-50 px-4 py-3">
                <MessageSquareMore className="mt-0.5 size-4 text-orange-500" />
                <span>
                  Playback completion insight from the prompt callback log.
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
