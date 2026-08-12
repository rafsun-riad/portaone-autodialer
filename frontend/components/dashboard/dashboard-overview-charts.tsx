"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  CheckCircle2,
  CircleSlash,
  PhoneMissed,
  PieChart as PieChartIcon,
} from "lucide-react";
import { useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Pie,
  PieChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { apiRequest } from "@/lib/client-api";
import { APP_TIMEZONE } from "@/lib/env";

type EntityId = string;

type PaginatedResponse<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

type CampaignOption = {
  id: EntityId;
  name: string;
  status: string;
};

type AnalyticsPoint = {
  bucket: string;
  success: number;
  invalid_number: number;
  not_answered: number;
  ongoing: number;
};

type CampaignAnalyticsResponse = {
  campaign: {
    id: EntityId;
    name: string;
    status: string;
    started_at: string | null;
    finished_at: string | null;
  };
  filters: {
    current_status: string;
    derived_status: string;
    bucket: "hour" | "day";
  };
  summary: {
    counts: {
      total_calls: number;
      ongoing_calls: number;
      classified_calls: number;
      success_calls: number;
      invalid_number_calls: number;
      not_answered_calls: number;
    };
    rates: {
      success_rate: number;
      invalid_number_rate: number;
      not_answered_rate: number;
    };
  };
  timeline: AnalyticsPoint[];
};

const currentStatusOptions = [
  "trying",
  "ringing",
  "early",
  "connected",
  "held",
  "holding",
  "queued",
  "dequeued",
  "transferred",
  "parked",
  "terminated",
  "failed",
] as const;

const overviewChartConfig = {
  success: {
    label: "Success",
    color: "#059669",
  },
  invalid_number: {
    label: "Invalid Number",
    color: "#e11d48",
  },
  not_answered: {
    label: "Not Answered",
    color: "#d97706",
  },
  ongoing: {
    label: "Ongoing",
    color: "#0f766e",
  },
} satisfies ChartConfig;

function formatLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatBucket(
  value: string,
  bucket: "hour" | "day",
  includeYear = false,
) {
  const date = new Date(value);

  return new Intl.DateTimeFormat("en-US", {
    timeZone: APP_TIMEZONE,
    month: "short",
    day: "numeric",
    ...(bucket === "hour"
      ? { hour: "numeric", minute: "2-digit" }
      : includeYear
        ? { year: "numeric" }
        : {}),
  }).format(date);
}

function summaryTone(status: keyof typeof overviewChartConfig) {
  if (status === "success") {
    return "bg-emerald-50 text-emerald-700 border-emerald-200";
  }
  if (status === "invalid_number") {
    return "bg-rose-50 text-rose-700 border-rose-200";
  }
  if (status === "not_answered") {
    return "bg-amber-50 text-amber-700 border-amber-200";
  }
  return "bg-teal-50 text-teal-700 border-teal-200";
}

export function DashboardOverviewCharts() {
  const [requestedCampaignId, setRequestedCampaignId] = useState<string>("");
  const [currentStatus, setCurrentStatus] = useState("");
  const [derivedStatus, setDerivedStatus] = useState("");
  const [bucket, setBucket] = useState<"auto" | "hour" | "day">("auto");

  const campaignsQuery = useQuery({
    queryKey: ["dashboard-overview-campaigns"],
    queryFn: () =>
      apiRequest<PaginatedResponse<CampaignOption>>(
        "/api/backend/campaigns/?page_size=200",
      ),
    refetchInterval: 15000,
    refetchIntervalInBackground: true,
  });

  const campaigns = campaignsQuery.data?.results ?? [];
  const selectedCampaignId = campaigns.some(
    (campaign) => campaign.id === requestedCampaignId,
  )
    ? requestedCampaignId
    : (campaigns[0]?.id ?? "");

  const analyticsQuery = useQuery({
    queryKey: [
      "dashboard-overview-analytics",
      selectedCampaignId,
      currentStatus,
      derivedStatus,
      bucket,
    ],
    enabled: Boolean(selectedCampaignId),
    queryFn: () => {
      const params = new URLSearchParams();
      if (currentStatus) {
        params.set("current_status", currentStatus);
      }
      if (derivedStatus) {
        params.set("derived_status", derivedStatus);
      }
      if (bucket !== "auto") {
        params.set("bucket", bucket);
      }

      const suffix = params.toString();
      return apiRequest<CampaignAnalyticsResponse>(
        `/api/backend/campaigns/${selectedCampaignId}/calls/analytics/${suffix ? `?${suffix}` : ""}`,
      );
    },
    refetchInterval: selectedCampaignId ? 10000 : false,
    refetchIntervalInBackground: true,
  });

  const analytics = analyticsQuery.data;
  const summary = analytics?.summary;
  const timeline = analytics?.timeline ?? [];
  const activeBucket = analytics?.filters.bucket ?? "hour";
  const selectedCampaign = campaigns.find(
    (campaign) => campaign.id === selectedCampaignId,
  );
  const classifiedCalls = analytics?.summary.counts.classified_calls ?? 0;
  const pieData = [
    {
      status: "success",
      calls: analytics?.summary.counts.success_calls ?? 0,
      fill: "var(--color-success)",
    },
    {
      status: "invalid_number",
      calls: analytics?.summary.counts.invalid_number_calls ?? 0,
      fill: "var(--color-invalid_number)",
    },
    {
      status: "not_answered",
      calls: analytics?.summary.counts.not_answered_calls ?? 0,
      fill: "var(--color-not_answered)",
    },
  ].filter((item) => item.calls > 0);

  const showEmptyCampaignState =
    !campaignsQuery.isLoading && campaigns.length === 0;

  return (
    <div className="dashboard-panel overflow-hidden p-6">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <p className="section-heading">Overview</p>
          <h3 className="mt-2 text-2xl font-semibold text-slate-950">
            Campaign telemetry by call outcome.
          </h3>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Select a campaign to watch outcome counts over time, isolate the
            same statuses used on the call log page, and compare success share
            against invalid and missed calls.
          </p>
        </div>
        <div className="rounded-full bg-[linear-gradient(135deg,rgba(15,118,110,0.12),rgba(56,189,248,0.12))] px-4 py-2 text-sm font-medium text-teal-700">
          {selectedCampaign
            ? `${selectedCampaign.status} campaign`
            : "Awaiting campaign"}
        </div>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        <label className="space-y-2 text-sm text-slate-600">
          <span className="font-medium text-slate-700">Campaign</span>
          <select
            className="dashboard-input-shell w-full rounded-2xl px-4 py-3 outline-none"
            value={selectedCampaignId}
            onChange={(event) => setRequestedCampaignId(event.target.value)}
            disabled={campaignsQuery.isLoading || showEmptyCampaignState}
          >
            {showEmptyCampaignState ? (
              <option value="">No campaigns found</option>
            ) : null}
            {campaigns.map((campaign) => (
              <option key={campaign.id} value={campaign.id}>
                {campaign.name}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-2 text-sm text-slate-600">
          <span className="font-medium text-slate-700">Current status</span>
          <select
            className="dashboard-input-shell w-full rounded-2xl px-4 py-3 outline-none"
            value={currentStatus}
            onChange={(event) => setCurrentStatus(event.target.value)}
            disabled={!selectedCampaignId}
          >
            <option value="">All current statuses</option>
            {currentStatusOptions.map((option) => (
              <option key={option} value={option}>
                {formatLabel(option)}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-2 text-sm text-slate-600">
          <span className="font-medium text-slate-700">Call status</span>
          <select
            className="dashboard-input-shell w-full rounded-2xl px-4 py-3 outline-none"
            value={derivedStatus}
            onChange={(event) => setDerivedStatus(event.target.value)}
            disabled={!selectedCampaignId}
          >
            <option value="">All outcomes</option>
            <option value="success">Success</option>
            <option value="invalid_number">Invalid Number</option>
            <option value="not_answered">Not Answered</option>
          </select>
        </label>

        <label className="space-y-2 text-sm text-slate-600">
          <span className="font-medium text-slate-700">Timeline density</span>
          <select
            className="dashboard-input-shell w-full rounded-2xl px-4 py-3 outline-none"
            value={bucket}
            onChange={(event) =>
              setBucket(event.target.value as "auto" | "hour" | "day")
            }
            disabled={!selectedCampaignId}
          >
            <option value="auto">Auto</option>
            <option value="hour">Hourly</option>
            <option value="day">Daily</option>
          </select>
        </label>
      </div>

      {selectedCampaignId && analytics ? (
        <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="data-card">
            <p className="text-sm font-medium text-slate-500">Total calls</p>
            <h4 className="mt-2 text-3xl font-semibold text-slate-950">
              {analytics.summary.counts.total_calls}
            </h4>
          </div>
          <div className="data-card">
            <p className="text-sm font-medium text-slate-500">Ongoing calls</p>
            <h4 className="mt-2 text-3xl font-semibold text-slate-950">
              {analytics.summary.counts.ongoing_calls}
            </h4>
          </div>
          <div className="data-card">
            <p className="text-sm font-medium text-slate-500">
              Classified calls
            </p>
            <h4 className="mt-2 text-3xl font-semibold text-slate-950">
              {analytics.summary.counts.classified_calls}
            </h4>
          </div>
          <div className="data-card">
            <p className="text-sm font-medium text-slate-500">Timeline mode</p>
            <h4 className="mt-2 text-3xl font-semibold capitalize text-slate-950">
              {activeBucket}
            </h4>
          </div>
        </div>
      ) : null}

      <div className="mt-6 grid gap-5 xl:grid-cols-[1.6fr_0.9fr]">
        <Card className="border-slate-200/80 bg-[linear-gradient(180deg,#ffffff,#f8fafc)] shadow-none">
          <CardHeader className="border-b border-slate-200/70 pb-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <CardTitle>Call activity area chart</CardTitle>
                <CardDescription>
                  Y-axis shows call counts and X-axis tracks Bangladesh time.
                </CardDescription>
              </div>
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-500">
                <Activity className="size-4 text-teal-600" />
                {selectedCampaignId
                  ? analyticsQuery.isFetching
                    ? "Refreshing"
                    : `${timeline.length} time slot${timeline.length === 1 ? "" : "s"}`
                  : "Select a campaign"}
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            {!selectedCampaignId ? (
              <div className="flex h-85 items-center justify-center rounded-[1.5rem] border border-dashed border-slate-200 bg-slate-50/70 px-6 text-center text-sm text-slate-500">
                Select a campaign to render call activity across time.
              </div>
            ) : analyticsQuery.isLoading ? (
              <div className="skeleton-block h-85 rounded-[1.5rem]" />
            ) : timeline.length === 0 ? (
              <div className="flex h-85 items-center justify-center rounded-[1.5rem] border border-dashed border-slate-200 bg-slate-50/70 px-6 text-center text-sm text-slate-500">
                No calls match the selected filters yet.
              </div>
            ) : (
              <ChartContainer
                config={overviewChartConfig}
                className="h-85 w-full"
              >
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    accessibilityLayer
                    data={timeline}
                    margin={{ top: 12, right: 12, left: 0, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient
                        id="fillSuccess"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="5%"
                          stopColor="var(--color-success)"
                          stopOpacity={0.45}
                        />
                        <stop
                          offset="95%"
                          stopColor="var(--color-success)"
                          stopOpacity={0.06}
                        />
                      </linearGradient>
                      <linearGradient
                        id="fillInvalid"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="5%"
                          stopColor="var(--color-invalid_number)"
                          stopOpacity={0.42}
                        />
                        <stop
                          offset="95%"
                          stopColor="var(--color-invalid_number)"
                          stopOpacity={0.05}
                        />
                      </linearGradient>
                      <linearGradient
                        id="fillNotAnswered"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="5%"
                          stopColor="var(--color-not_answered)"
                          stopOpacity={0.42}
                        />
                        <stop
                          offset="95%"
                          stopColor="var(--color-not_answered)"
                          stopOpacity={0.05}
                        />
                      </linearGradient>
                      <linearGradient
                        id="fillOngoing"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="5%"
                          stopColor="var(--color-ongoing)"
                          stopOpacity={0.36}
                        />
                        <stop
                          offset="95%"
                          stopColor="var(--color-ongoing)"
                          stopOpacity={0.04}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} />
                    <XAxis
                      dataKey="bucket"
                      axisLine={false}
                      tickLine={false}
                      tickMargin={10}
                      minTickGap={28}
                      tickFormatter={(value) =>
                        formatBucket(String(value), activeBucket)
                      }
                    />
                    <YAxis
                      allowDecimals={false}
                      axisLine={false}
                      tickLine={false}
                      tickMargin={10}
                    />
                    <ChartTooltip
                      cursor={false}
                      content={
                        <ChartTooltipContent
                          labelFormatter={(value) =>
                            formatBucket(String(value), activeBucket, true)
                          }
                        />
                      }
                    />
                    <Area
                      type="monotone"
                      dataKey="ongoing"
                      name="ongoing"
                      stroke="var(--color-ongoing)"
                      fill="url(#fillOngoing)"
                      strokeWidth={2}
                      stackId="calls"
                    />
                    <Area
                      type="monotone"
                      dataKey="not_answered"
                      name="not_answered"
                      stroke="var(--color-not_answered)"
                      fill="url(#fillNotAnswered)"
                      strokeWidth={2}
                      stackId="calls"
                    />
                    <Area
                      type="monotone"
                      dataKey="invalid_number"
                      name="invalid_number"
                      stroke="var(--color-invalid_number)"
                      fill="url(#fillInvalid)"
                      strokeWidth={2}
                      stackId="calls"
                    />
                    <Area
                      type="monotone"
                      dataKey="success"
                      name="success"
                      stroke="var(--color-success)"
                      fill="url(#fillSuccess)"
                      strokeWidth={2}
                      stackId="calls"
                    />
                    <ChartLegend content={<ChartLegendContent />} />
                  </AreaChart>
                </ResponsiveContainer>
              </ChartContainer>
            )}
          </CardContent>
        </Card>

        <Card className="border-slate-200/80 bg-[linear-gradient(180deg,#ffffff,#f8fafc)] shadow-none">
          <CardHeader className="border-b border-slate-200/70 pb-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle>Outcome share</CardTitle>
                <CardDescription>
                  Success, invalid number, and not answered percentages.
                </CardDescription>
              </div>
              <div className="rounded-full bg-slate-100 p-2 text-slate-500">
                <PieChartIcon className="size-4" />
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            {!selectedCampaignId ? (
              <div className="flex h-85 items-center justify-center rounded-[1.5rem] border border-dashed border-slate-200 bg-slate-50/70 px-6 text-center text-sm text-slate-500">
                Choose a campaign to compare outcome percentages.
              </div>
            ) : analyticsQuery.isLoading ? (
              <div className="skeleton-block h-85 rounded-[1.5rem]" />
            ) : classifiedCalls === 0 ? (
              <div className="flex h-85 items-center justify-center rounded-[1.5rem] border border-dashed border-slate-200 bg-slate-50/70 px-6 text-center text-sm text-slate-500">
                Classified call outcomes will appear here after completed calls
                land.
              </div>
            ) : (
              <div className="space-y-5">
                <ChartContainer
                  config={overviewChartConfig}
                  className="mx-auto h-60 max-w-70"
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart accessibilityLayer>
                      <ChartTooltip
                        content={
                          <ChartTooltipContent hideLabel nameKey="status" />
                        }
                      />
                      <Pie
                        data={pieData}
                        dataKey="calls"
                        nameKey="status"
                        innerRadius={56}
                        outerRadius={94}
                        strokeWidth={4}
                      >
                        {/* <LabelList
                          dataKey="status"
                          stroke="none"
                          fontSize={11}
                          formatter={(value) =>
                            overviewChartConfig[
                              String(value) as keyof typeof overviewChartConfig
                            ]?.label
                          }
                        /> */}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                </ChartContainer>

                <div className="grid gap-3">
                  <div
                    className={`flex items-center justify-between rounded-2xl border px-4 py-3 ${summaryTone("success")}`}
                  >
                    <div className="flex items-center gap-3">
                      <CheckCircle2 className="size-4" />
                      <span className="font-medium">Success</span>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold">
                        {(summary?.rates.success_rate ?? 0).toFixed(2)}%
                      </div>
                      <div className="text-xs opacity-80">
                        {summary?.counts.success_calls ?? 0} calls
                      </div>
                    </div>
                  </div>
                  <div
                    className={`flex items-center justify-between rounded-2xl border px-4 py-3 ${summaryTone("invalid_number")}`}
                  >
                    <div className="flex items-center gap-3">
                      <CircleSlash className="size-4" />
                      <span className="font-medium">Invalid Number</span>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold">
                        {(summary?.rates.invalid_number_rate ?? 0).toFixed(2)}%
                      </div>
                      <div className="text-xs opacity-80">
                        {summary?.counts.invalid_number_calls ?? 0} calls
                      </div>
                    </div>
                  </div>
                  <div
                    className={`flex items-center justify-between rounded-2xl border px-4 py-3 ${summaryTone("not_answered")}`}
                  >
                    <div className="flex items-center gap-3">
                      <PhoneMissed className="size-4" />
                      <span className="font-medium">Not Answered</span>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold">
                        {(summary?.rates.not_answered_rate ?? 0).toFixed(2)}%
                      </div>
                      <div className="text-xs opacity-80">
                        {summary?.counts.not_answered_calls ?? 0} calls
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
