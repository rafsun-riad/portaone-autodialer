"use client";

import { Button } from "@heroui/react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Ban,
  CalendarClock,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  PhoneMissed,
  RotateCcw,
  Search,
  Users,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useDeferredValue, useEffect, useState, useTransition } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Dialog } from "@/components/ui/dialog";
import { apiRequest } from "@/lib/client-api";
import {
  formatDhakaDateTime,
  formatDhakaDateTimeWithSeconds,
  fromDhakaInputValue,
} from "@/lib/time";

type EntityId = string;

type PaginatedResponse<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
  summary?: CampaignCallLogSummary;
};

type CampaignOption = {
  id: EntityId;
  name: string;
  status: string;
};

type CampaignCallLog = {
  id: EntityId;
  campaign_name: string;
  campaign_started_at: string | null;
  campaign_finished_at: string | null;
  external_call_id: string;
  status: string;
  derived_status: "success" | "invalid_number" | "not_answered" | "other";
  account_id: string;
  caller_id: string;
  destination: string;
  reason: string;
  reason_code: number | null;
  duration: number;
  connect_time: string | null;
  playback_requested_at: string | null;
  playback_completed_at: string | null;
};

type CampaignCallLogSummary = {
  campaign: {
    id: EntityId;
    name: string;
    status: string;
    started_at: string | null;
    finished_at: string | null;
  };
  counts: {
    ongoing_calls: number;
    contact_count: number;
    completed_calls: number;
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

const restartSchema = z
  .object({
    restart_scope: z.enum(["all", "not_answered", "exclude_invalid"]),
    run_mode: z.enum(["immediate", "scheduled"]),
    scheduled_at: z.string().optional(),
  })
  .superRefine((values, context) => {
    if (values.run_mode === "scheduled" && !values.scheduled_at) {
      context.addIssue({
        code: "custom",
        path: ["scheduled_at"],
        message: "Choose a Bangladesh time for the restart.",
      });
    }
  });

type RestartValues = z.infer<typeof restartSchema>;

function formatLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatDuration(seconds: number) {
  if (!seconds) {
    return "0s";
  }

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainingSeconds = seconds % 60;
  const parts: string[] = [];

  if (hours) {
    parts.push(`${hours}h`);
  }
  if (minutes) {
    parts.push(`${minutes}m`);
  }
  if (remainingSeconds || parts.length === 0) {
    parts.push(`${remainingSeconds}s`);
  }

  return parts.join(" ");
}

function statusTone(status: CampaignCallLog["derived_status"]) {
  if (status === "success") {
    return "bg-emerald-50 text-emerald-700 border-emerald-200";
  }
  if (status === "invalid_number") {
    return "bg-rose-50 text-rose-700 border-rose-200";
  }
  if (status === "not_answered") {
    return "bg-amber-50 text-amber-700 border-amber-200";
  }
  return "bg-slate-100 text-slate-600 border-slate-200";
}

function RateBar({
  label,
  value,
  count,
  toneClassName,
}: {
  label: string;
  value: number;
  count: number;
  toneClassName: string;
}) {
  return (
    <div className="data-card">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-slate-500">{label}</p>
          <h3 className="mt-2 text-2xl font-semibold text-slate-950">
            {value.toFixed(2)}%
          </h3>
        </div>
        <div className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
          {count} calls
        </div>
      </div>
      <div className="mt-4 h-3 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full ${toneClassName}`}
          style={{ width: `${Math.min(value, 100)}%` }}
        />
      </div>
    </div>
  );
}

export function CampaignCallLogsPageClient({
  initialCampaignId,
}: {
  initialCampaignId: string;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [isNavigating, startTransition] = useTransition();
  const [selectedCampaignId, setSelectedCampaignId] =
    useState(initialCampaignId);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [currentStatus, setCurrentStatus] = useState("");
  const [derivedStatus, setDerivedStatus] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [restartOpen, setRestartOpen] = useState(false);
  const deferredSearch = useDeferredValue(search);

  const restartForm = useForm<RestartValues>({
    resolver: zodResolver(restartSchema),
    defaultValues: {
      restart_scope: "all",
      run_mode: "immediate",
      scheduled_at: "",
    },
  });
  const selectedRestartScope = useWatch({
    control: restartForm.control,
    name: "restart_scope",
  });
  const selectedRunMode = useWatch({
    control: restartForm.control,
    name: "run_mode",
  });

  const campaignsQuery = useQuery({
    queryKey: ["call-log-campaigns"],
    queryFn: () =>
      apiRequest<PaginatedResponse<CampaignOption>>(
        "/api/backend/campaigns/?page_size=200",
      ),
    refetchInterval: 15000,
    refetchIntervalInBackground: true,
  });

  const activeCampaignId =
    selectedCampaignId ||
    initialCampaignId ||
    campaignsQuery.data?.results[0]?.id ||
    null;

  const callLogsQuery = useQuery({
    queryKey: [
      "campaign-call-logs",
      activeCampaignId,
      page,
      deferredSearch,
      currentStatus,
      derivedStatus,
    ],
    enabled: Boolean(activeCampaignId),
    queryFn: () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: "100",
      });
      if (deferredSearch) {
        params.set("search", deferredSearch);
      }
      if (currentStatus) {
        params.set("current_status", currentStatus);
      }
      if (derivedStatus) {
        params.set("derived_status", derivedStatus);
      }

      return apiRequest<PaginatedResponse<CampaignCallLog>>(
        `/api/backend/campaigns/${activeCampaignId}/calls/?${params.toString()}`,
      );
    },
    refetchInterval: activeCampaignId ? 5000 : false,
    refetchIntervalInBackground: true,
  });

  const restartMutation = useMutation({
    mutationFn: (values: RestartValues) => {
      if (!activeCampaignId) {
        throw new Error("Select a campaign first.");
      }

      return apiRequest<{
        selected_contact_count: number;
      }>(`/api/backend/campaigns/${activeCampaignId}/restart/`, {
        method: "POST",
        body: {
          restart_scope: values.restart_scope,
          run_mode: values.run_mode,
          scheduled_at:
            values.run_mode === "scheduled" && values.scheduled_at
              ? fromDhakaInputValue(values.scheduled_at)
              : null,
        },
      });
    },
    onSuccess: (data, values) => {
      setRestartOpen(false);
      restartForm.reset({
        restart_scope: values.restart_scope,
        run_mode: "immediate",
        scheduled_at: "",
      });
      setNotice(
        values.run_mode === "scheduled"
          ? `Restart scheduled for ${data.selected_contact_count} contacts.`
          : `Campaign restarted for ${data.selected_contact_count} contacts.`,
      );
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      queryClient.invalidateQueries({ queryKey: ["call-log-campaigns"] });
      queryClient.invalidateQueries({
        queryKey: ["campaign-call-logs", activeCampaignId],
      });
    },
    onError: (error) => {
      setNotice(
        error instanceof Error
          ? error.message
          : "Unable to restart the campaign.",
      );
    },
  });

  useEffect(() => {
    if (!activeCampaignId) {
      return;
    }

    startTransition(() => {
      router.replace(`/call-logs?campaignId=${activeCampaignId}`);
    });
  }, [activeCampaignId, router]);

  const selectedCampaign = campaignsQuery.data?.results.find(
    (campaign) => campaign.id === activeCampaignId,
  );
  const summary = callLogsQuery.data?.summary;
  const pageCount = Math.max(
    1,
    Math.ceil((callLogsQuery.data?.count ?? 0) / 100),
  );

  return (
    <div className="space-y-6">
      <div className="dashboard-panel flex flex-col gap-4 p-6 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="section-heading">Campaign analytics</p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950">
            Campaign Call Logs
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-600">
            Review campaign call outcomes, isolate not answered or invalid
            numbers, and trigger a controlled restart without leaving the
            operator workspace.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button variant="secondary" isDisabled>
            <Download className="size-4" />
            Export CSV
          </Button>
          <Button
            onPress={() => setRestartOpen(true)}
            isDisabled={!activeCampaignId || restartMutation.isPending}
          >
            <RotateCcw className="size-4" />
            Restart campaign
          </Button>
        </div>
      </div>

      {notice ? (
        <div className="dashboard-inline-notice rounded-2xl px-4 py-3 text-sm text-teal-900">
          {notice}
        </div>
      ) : null}

      <section className="dashboard-panel p-5">
        <div className="grid gap-4 xl:grid-cols-[1.1fr_1fr_0.8fr_0.8fr]">
          <label className="space-y-2 text-sm text-slate-600">
            <span className="font-medium text-slate-700">Campaign</span>
            <select
              className="dashboard-input-shell w-full rounded-2xl px-4 py-3 outline-none"
              value={activeCampaignId ?? ""}
              onChange={(event) => {
                setSelectedCampaignId(event.target.value);
                setPage(1);
              }}
            >
              <option value="">Select a campaign</option>
              {campaignsQuery.data?.results.map((campaign) => (
                <option key={campaign.id} value={campaign.id}>
                  {campaign.name}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-2 text-sm text-slate-600">
            <span className="font-medium text-slate-700">Search by number</span>
            <div className="dashboard-input-shell flex items-center gap-3 rounded-2xl px-4 py-3">
              <Search className="size-4 text-slate-400" />
              <input
                className="w-full bg-transparent outline-none"
                placeholder="8801..."
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
                type="search"
              />
            </div>
          </label>

          <label className="space-y-2 text-sm text-slate-600">
            <span className="font-medium text-slate-700">Current status</span>
            <select
              className="dashboard-input-shell w-full rounded-2xl px-4 py-3 outline-none"
              value={currentStatus}
              onChange={(event) => {
                setCurrentStatus(event.target.value);
                setPage(1);
              }}
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
              onChange={(event) => {
                setDerivedStatus(event.target.value);
                setPage(1);
              }}
            >
              <option value="">All outcomes</option>
              <option value="success">Success</option>
              <option value="invalid_number">Invalid Number</option>
              <option value="not_answered">Not Answered</option>
            </select>
          </label>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="dashboard-stat-card">
          <div className="dashboard-stat-icon bg-[linear-gradient(135deg,#0f766e,#14b8a6)] text-white">
            <Activity className="size-4" />
          </div>
          <p className="mt-5 text-sm font-medium text-slate-500">
            Ongoing calls
          </p>
          <h2 className="mt-2 text-4xl font-semibold tracking-tight text-slate-950">
            {summary?.counts.ongoing_calls ?? 0}
          </h2>
        </div>

        <div className="dashboard-stat-card">
          <div className="dashboard-stat-icon bg-[linear-gradient(135deg,#4f46e5,#818cf8)] text-white">
            <Users className="size-4" />
          </div>
          <p className="mt-5 text-sm font-medium text-slate-500">
            Campaign contacts
          </p>
          <h2 className="mt-2 text-4xl font-semibold tracking-tight text-slate-950">
            {summary?.counts.contact_count ?? 0}
          </h2>
        </div>

        <div className="dashboard-stat-card">
          <div className="dashboard-stat-icon bg-[linear-gradient(135deg,#f97316,#fb7185)] text-white">
            <CheckCircle2 className="size-4" />
          </div>
          <p className="mt-5 text-sm font-medium text-slate-500">
            Completed calls
          </p>
          <h2 className="mt-2 text-4xl font-semibold tracking-tight text-slate-950">
            {summary?.counts.completed_calls ?? 0}
          </h2>
        </div>

        <div className="dashboard-stat-card">
          <div className="dashboard-stat-icon bg-[linear-gradient(135deg,#7c3aed,#ec4899)] text-white">
            <CalendarClock className="size-4" />
          </div>
          <p className="mt-5 text-sm font-medium text-slate-500">
            Campaign status
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
            {formatLabel(
              summary?.campaign.status ?? selectedCampaign?.status ?? "new",
            )}
          </h2>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        <RateBar
          label="Success rate"
          value={summary?.rates.success_rate ?? 0}
          count={summary?.counts.success_calls ?? 0}
          toneClassName="bg-[linear-gradient(90deg,#10b981,#34d399)]"
        />
        <RateBar
          label="Invalid number rate"
          value={summary?.rates.invalid_number_rate ?? 0}
          count={summary?.counts.invalid_number_calls ?? 0}
          toneClassName="bg-[linear-gradient(90deg,#f43f5e,#fb7185)]"
        />
        <RateBar
          label="Not answered rate"
          value={summary?.rates.not_answered_rate ?? 0}
          count={summary?.counts.not_answered_calls ?? 0}
          toneClassName="bg-[linear-gradient(90deg,#f59e0b,#fbbf24)]"
        />
      </section>

      <section className="dashboard-panel overflow-hidden">
        <div className="flex flex-col gap-4 border-b border-slate-200 px-5 py-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="section-heading">Call log table</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-950">
              {summary?.campaign.name ??
                selectedCampaign?.name ??
                "Campaign call logs"}
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              100 logs per page. Current status stays visible under each derived
              outcome badge so the external system state is preserved.
            </p>
          </div>
          <div className="rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-500">
            {callLogsQuery.data?.count ?? 0} matching logs
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                {[
                  "Campaign Name",
                  "Campaign Start Time",
                  "Campaign Finish Time",
                  "PortaOne Call ID",
                  "Account ID",
                  "Caller ID",
                  "Destination",
                  "Reason",
                  "Reason Code",
                  "Received Time",
                  "Duration",
                  "Playback Requested Time",
                  "Playback Completed Time",
                  "Status",
                ].map((header) => (
                  <th
                    key={header}
                    className="border-b border-slate-200 px-4 py-3 font-semibold"
                  >
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {callLogsQuery.isLoading ? (
                Array.from({ length: 5 }).map((_, index) => (
                  <tr key={`skeleton-${index}`}>
                    <td
                      colSpan={14}
                      className="border-b border-slate-100 px-4 py-3"
                    >
                      <div className="skeleton-block h-12" />
                    </td>
                  </tr>
                ))
              ) : callLogsQuery.data?.results.length ? (
                callLogsQuery.data.results.map((log) => (
                  <tr key={log.id} className="align-top text-slate-700">
                    <td className="border-b border-slate-100 px-4 py-3 font-medium text-slate-900">
                      {log.campaign_name}
                    </td>
                    <td className="border-b border-slate-100 px-4 py-3">
                      {formatDhakaDateTimeWithSeconds(log.campaign_started_at)}
                    </td>
                    <td className="border-b border-slate-100 px-4 py-3">
                      {formatDhakaDateTimeWithSeconds(log.campaign_finished_at)}
                    </td>
                    <td className="border-b border-slate-100 px-4 py-3 font-medium text-slate-900">
                      {log.external_call_id || "-"}
                    </td>
                    <td className="border-b border-slate-100 px-4 py-3">
                      {log.account_id || "-"}
                    </td>
                    <td className="border-b border-slate-100 px-4 py-3">
                      {log.caller_id || "-"}
                    </td>
                    <td className="border-b border-slate-100 px-4 py-3">
                      {log.destination || "-"}
                    </td>
                    <td className="border-b border-slate-100 px-4 py-3">
                      <div className="max-w-52 space-y-1">
                        <p>{log.reason || "-"}</p>
                        <p className="text-xs text-slate-400">
                          Current status: {formatLabel(log.status || "unknown")}
                        </p>
                      </div>
                    </td>
                    <td className="border-b border-slate-100 px-4 py-3">
                      {log.reason_code ?? "-"}
                    </td>
                    <td className="border-b border-slate-100 px-4 py-3">
                      {formatDhakaDateTimeWithSeconds(log.connect_time)}
                    </td>
                    <td className="border-b border-slate-100 px-4 py-3">
                      {formatDuration(log.duration)}
                    </td>
                    <td className="border-b border-slate-100 px-4 py-3">
                      {formatDhakaDateTime(log.playback_requested_at)}
                    </td>
                    <td className="border-b border-slate-100 px-4 py-3">
                      {formatDhakaDateTime(log.playback_completed_at)}
                    </td>
                    <td className="border-b border-slate-100 px-4 py-3">
                      <span
                        className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] ${statusTone(log.derived_status)}`}
                      >
                        {formatLabel(log.derived_status)}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td
                    colSpan={14}
                    className="px-4 py-12 text-center text-sm text-slate-500"
                  >
                    {activeCampaignId
                      ? "No call logs match the current filters."
                      : "Select a campaign to load call logs."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-slate-500">
            Page {page} of {pageCount}
            {isNavigating ? " updating..." : ""}
          </p>
          <div className="flex gap-3">
            <Button
              variant="secondary"
              onPress={() =>
                setPage((currentPage) => Math.max(1, currentPage - 1))
              }
              isDisabled={page <= 1}
            >
              <ChevronLeft className="size-4" />
              Previous
            </Button>
            <Button
              variant="secondary"
              onPress={() =>
                setPage((currentPage) => Math.min(pageCount, currentPage + 1))
              }
              isDisabled={page >= pageCount}
            >
              Next
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      </section>

      <Dialog
        open={restartOpen}
        onClose={() => setRestartOpen(false)}
        title="Restart campaign"
        description="Choose which numbers should be re-queued and whether the restart should run now or at a scheduled Bangladesh time."
        footer={
          <>
            <Button variant="secondary" onPress={() => setRestartOpen(false)}>
              Cancel
            </Button>
            <Button
              onPress={restartForm.handleSubmit((values) =>
                restartMutation.mutate(values),
              )}
              isLoading={restartMutation.isPending}
            >
              Confirm restart
            </Button>
          </>
        }
      >
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-3">
            {[
              {
                value: "all",
                label: "All numbers",
                description: "Restart every contact in the campaign.",
                icon: RotateCcw,
              },
              {
                value: "not_answered",
                label: "Only not answered",
                description: "Retry only numbers classified as not answered.",
                icon: PhoneMissed,
              },
              {
                value: "exclude_invalid",
                label: "Exclude invalid",
                description: "Restart all contacts except invalid numbers.",
                icon: Ban,
              },
            ].map((option) => {
              const Icon = option.icon;
              const isSelected = selectedRestartScope === option.value;

              return (
                <button
                  key={option.value}
                  className={`rounded-[1.6rem] border p-4 text-left transition ${
                    isSelected
                      ? "border-teal-300 bg-teal-50"
                      : "border-slate-200 bg-slate-50 hover:border-teal-200"
                  }`}
                  type="button"
                  onClick={() =>
                    restartForm.setValue(
                      "restart_scope",
                      option.value as RestartValues["restart_scope"],
                    )
                  }
                >
                  <div className="flex items-center gap-3">
                    <span className="flex size-10 items-center justify-center rounded-full bg-white text-slate-700 shadow-[0_10px_25px_rgba(15,23,42,0.08)]">
                      <Icon className="size-4" />
                    </span>
                    <div>
                      <p className="font-semibold text-slate-950">
                        {option.label}
                      </p>
                      <p className="mt-1 text-xs leading-6 text-slate-500">
                        {option.description}
                      </p>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="grid gap-4 lg:grid-cols-[0.7fr_1.3fr]">
            <div className="space-y-2 text-sm text-slate-600">
              <p className="font-medium text-slate-700">Run mode</p>
              <div className="flex gap-3">
                <button
                  type="button"
                  className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
                    selectedRunMode === "immediate"
                      ? "border-teal-300 bg-teal-50 text-teal-700"
                      : "border-slate-200 bg-white text-slate-600"
                  }`}
                  onClick={() => restartForm.setValue("run_mode", "immediate")}
                >
                  Restart now
                </button>
                <button
                  type="button"
                  className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
                    selectedRunMode === "scheduled"
                      ? "border-teal-300 bg-teal-50 text-teal-700"
                      : "border-slate-200 bg-white text-slate-600"
                  }`}
                  onClick={() => restartForm.setValue("run_mode", "scheduled")}
                >
                  Schedule restart
                </button>
              </div>
            </div>

            <label className="space-y-2 text-sm text-slate-600">
              <span className="font-medium text-slate-700">Scheduled time</span>
              <input
                type="datetime-local"
                className="dashboard-input-shell w-full rounded-2xl px-4 py-3 outline-none"
                disabled={selectedRunMode !== "scheduled"}
                {...restartForm.register("scheduled_at")}
              />
              <p className="text-xs text-slate-500">
                Time is stored and displayed in Asia/Dhaka.
              </p>
              {restartForm.formState.errors.scheduled_at ? (
                <p className="text-xs text-rose-600">
                  {restartForm.formState.errors.scheduled_at.message}
                </p>
              ) : null}
            </label>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
