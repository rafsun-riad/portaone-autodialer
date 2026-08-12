import { fetchBackendJson } from "@/lib/server-api";
import { formatDhakaDateTime } from "@/lib/time";
import {
  ChartColumnBig,
  Clock3,
  Radio,
  ShieldCheck,
  Wallet,
} from "lucide-react";

import { DashboardOverviewCharts } from "@/components/dashboard/dashboard-overview-charts";

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
                {displayName}
              </p>
            </div>
          </div>
        </div>
      </header>
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

      <section>
        <DashboardOverviewCharts />
      </section>
    </div>
  );
}
