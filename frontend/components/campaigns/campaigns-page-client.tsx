"use client";

import { Button } from "@heroui/react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Pause,
  Pencil,
  PhoneCall,
  Play,
  Plus,
  RotateCcw,
  Search,
  Square,
  Trash2,
  UserRoundSearch,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Dialog } from "@/components/ui/dialog";
import { apiRequest } from "@/lib/client-api";
import {
  formatDhakaDateTime,
  fromDhakaInputValue,
  toDhakaInputValue,
} from "@/lib/time";
import { useAppStore } from "@/stores/app-store";

type PaginatedResponse<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

type Campaign = {
  id: number;
  name: string;
  status: string;
  connect_to: string;
  scheduled_at: string | null;
  campaign_pace: number;
  description: string;
  billable_account: string;
  caller_id: string;
  ongoing_calls: number;
  contact_count: number;
  completed_contacts: number;
  audio: {
    id: number;
    original_name: string;
    file_url: string;
  } | null;
};

type AccountOption = {
  connect_to: string;
  billable_account: string;
  caller_id: string;
  label: string;
};

type CallLog = {
  id: number;
  status: string;
  destination: string;
  duration: number;
  reason: string;
  contact_name: string | null;
  update_time: string | null;
};

const campaignStatuses = [
  "new",
  "scheduled",
  "processing",
  "paused",
  "finished",
  "overdue",
  "canceled",
] as const;

const campaignSchema = z.object({
  name: z.string().min(2, "Name is required."),
  status: z.enum(campaignStatuses),
  connect_to: z.string().min(1, "Choose a connect-to account."),
  scheduled_at: z.string().optional(),
  campaign_pace: z.number().int().min(1, "Campaign pace must be at least 1."),
  description: z.string().optional(),
  billable_account: z.string().min(1, "Billable account is required."),
  caller_id: z.string().min(1, "Caller ID is required."),
});

type CampaignValues = z.infer<typeof campaignSchema>;

function TableSkeleton() {
  return (
    <div className="space-y-3">
      <div className="skeleton-block h-14" />
      <div className="skeleton-block h-14" />
      <div className="skeleton-block h-14" />
      <div className="skeleton-block h-14" />
    </div>
  );
}

export function CampaignsPageClient() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const campaignSearch = useAppStore((state) => state.campaignSearch);
  const setCampaignSearch = useAppStore((state) => state.setCampaignSearch);
  const [page, setPage] = useState(1);
  const [formOpen, setFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [editingCampaign, setEditingCampaign] = useState<Campaign | null>(null);
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(
    null,
  );
  const [notice, setNotice] = useState<string | null>(null);

  const form = useForm<CampaignValues>({
    resolver: zodResolver(campaignSchema),
    defaultValues: {
      name: "",
      status: "new",
      connect_to: "",
      scheduled_at: "",
      campaign_pace: 1,
      description: "",
      billable_account: "",
      caller_id: "",
    },
  });

  const campaignsQuery = useQuery({
    queryKey: ["campaigns", page, campaignSearch],
    queryFn: () =>
      apiRequest<PaginatedResponse<Campaign>>(
        `/api/backend/campaigns/?page=${page}&search=${encodeURIComponent(campaignSearch)}`,
      ),
  });

  const accountOptionsQuery = useQuery({
    queryKey: ["campaign-account-options"],
    queryFn: () =>
      apiRequest<{ options: AccountOption[] }>(
        "/api/backend/accounts/options/",
      ),
  });

  const callLogQuery = useQuery({
    queryKey: ["campaign-calls", selectedCampaign?.id],
    enabled: Boolean(selectedCampaign),
    queryFn: () =>
      apiRequest<PaginatedResponse<CallLog>>(
        `/api/backend/campaigns/${selectedCampaign?.id}/calls/`,
      ),
  });

  const saveMutation = useMutation({
    mutationFn: (values: CampaignValues) => {
      const payload = {
        ...values,
        scheduled_at: values.scheduled_at
          ? fromDhakaInputValue(values.scheduled_at)
          : null,
      };

      if (editingCampaign) {
        return apiRequest<Campaign>(
          `/api/backend/campaigns/${editingCampaign.id}/`,
          {
            method: "PATCH",
            body: payload,
          },
        );
      }

      return apiRequest<Campaign>("/api/backend/campaigns/", {
        method: "POST",
        body: payload,
      });
    },
    onSuccess: () => {
      setNotice(editingCampaign ? "Campaign updated." : "Campaign created.");
      setFormOpen(false);
      setEditingCampaign(null);
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    },
    onError: (error) => {
      setNotice(
        error instanceof Error ? error.message : "Unable to save the campaign.",
      );
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (campaignId: number) =>
      apiRequest<void>(`/api/backend/campaigns/${campaignId}/`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      setNotice("Campaign deleted.");
      setDetailOpen(false);
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    },
  });

  const actionMutation = useMutation({
    mutationFn: ({
      campaignId,
      action,
    }: {
      campaignId: number;
      action: string;
    }) =>
      apiRequest<Campaign>(
        `/api/backend/campaigns/${campaignId}/actions/${action}/`,
        {
          method: "POST",
        },
      ),
    onSuccess: (campaign) => {
      setSelectedCampaign(campaign);
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      queryClient.invalidateQueries({
        queryKey: ["campaign-calls", campaign.id],
      });
      setNotice(`Campaign ${campaign.status}.`);
    },
    onError: (error) => {
      setNotice(
        error instanceof Error
          ? error.message
          : "Unable to perform that action.",
      );
    },
  });

  const connectTo = form.watch("connect_to");

  const actionVisibility = selectedCampaign
    ? {
        canStart: ["new", "scheduled", "overdue"].includes(
          selectedCampaign.status,
        ),
        canPause: selectedCampaign.status === "processing",
        canResume: selectedCampaign.status === "paused",
        canRestart: ["finished", "canceled"].includes(selectedCampaign.status),
        canStop: [
          "new",
          "scheduled",
          "overdue",
          "processing",
          "paused",
        ].includes(selectedCampaign.status),
      }
    : {
        canStart: false,
        canPause: false,
        canResume: false,
        canRestart: false,
        canStop: false,
      };

  useEffect(() => {
    const selectedOption = accountOptionsQuery.data?.options.find(
      (option) => option.connect_to === connectTo,
    );
    if (!selectedOption) {
      return;
    }

    form.setValue("billable_account", selectedOption.billable_account, {
      shouldDirty: true,
    });
    if (!editingCampaign || !form.getValues("caller_id")) {
      form.setValue("caller_id", selectedOption.caller_id, {
        shouldDirty: true,
      });
    }
  }, [accountOptionsQuery.data?.options, connectTo, editingCampaign, form]);

  const openCreate = () => {
    setEditingCampaign(null);
    form.reset({
      name: "",
      status: "new",
      connect_to: "",
      scheduled_at: "",
      campaign_pace: 1,
      description: "",
      billable_account: "",
      caller_id: "",
    });
    setFormOpen(true);
  };

  const openEdit = (campaign: Campaign) => {
    setEditingCampaign(campaign);
    form.reset({
      name: campaign.name,
      status: campaign.status as CampaignValues["status"],
      connect_to: campaign.connect_to,
      scheduled_at: toDhakaInputValue(campaign.scheduled_at),
      campaign_pace: campaign.campaign_pace,
      description: campaign.description,
      billable_account: campaign.billable_account,
      caller_id: campaign.caller_id,
    });
    setFormOpen(true);
  };

  const pageCount = Math.max(
    1,
    Math.ceil((campaignsQuery.data?.count ?? 0) / 10),
  );

  return (
    <div className="space-y-6">
      <div className="dashboard-panel flex flex-col gap-4 p-6 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="section-heading">Campaign registry</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-950">
            Manage call campaigns
          </h2>
          <p className="mt-2 text-sm leading-7 text-slate-600">
            Create user-specific campaigns, bind them to external accounts, and
            control campaign state changes from one table.
          </p>
        </div>
        <Button onPress={openCreate}>
          <Plus className="size-4" />
          New campaign
        </Button>
      </div>

      {notice ? (
        <div className="dashboard-inline-notice rounded-2xl px-4 py-3 text-sm text-teal-900">
          {notice}
        </div>
      ) : null}

      <section className="dashboard-panel grid gap-4 p-5 lg:grid-cols-[1fr_auto]">
        <div className="dashboard-input-shell flex items-center gap-3 px-4 py-3">
          <Search className="size-4 text-slate-400" />
          <input
            className="w-full bg-transparent outline-none"
            placeholder="Search campaigns by name"
            value={campaignSearch}
            onChange={(event) => {
              setCampaignSearch(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="dashboard-muted-chip rounded-2xl px-4 py-3 text-sm text-slate-600">
          Bangladesh/Dhaka schedule timezone
        </div>
      </section>

      <section className="dashboard-panel overflow-hidden">
        {campaignsQuery.isLoading ? (
          <div className="p-5">
            <TableSkeleton />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-5 py-4 font-medium">Name</th>
                  <th className="px-5 py-4 font-medium">Status</th>
                  <th className="px-5 py-4 font-medium">Connect To</th>
                  <th className="px-5 py-4 font-medium">Schedule</th>
                  <th className="px-5 py-4 font-medium">Pace</th>
                  <th className="px-5 py-4 font-medium">Ongoing</th>
                  <th className="px-5 py-4 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {campaignsQuery.data?.results.map((campaign) => (
                  <tr
                    key={campaign.id}
                    className="cursor-pointer transition hover:bg-slate-50"
                    onClick={() => {
                      setSelectedCampaign(campaign);
                      setDetailOpen(true);
                    }}
                  >
                    <td className="px-5 py-4 align-top">
                      <p className="font-medium text-slate-900">
                        {campaign.name}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {campaign.description || "No description"}
                      </p>
                    </td>
                    <td className="px-5 py-4 align-top">
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-700">
                        {campaign.status}
                      </span>
                    </td>
                    <td className="px-5 py-4 align-top text-slate-700">
                      {campaign.connect_to}
                    </td>
                    <td className="px-5 py-4 align-top text-slate-700">
                      {formatDhakaDateTime(campaign.scheduled_at)}
                    </td>
                    <td className="px-5 py-4 align-top text-slate-700">
                      {campaign.campaign_pace}/min
                    </td>
                    <td className="px-5 py-4 align-top text-slate-700">
                      {campaign.ongoing_calls}
                    </td>
                    <td className="px-5 py-4 align-top">
                      <div className="flex justify-end gap-2">
                        <button
                          className="rounded-full border border-slate-200 p-2 text-slate-500 transition hover:border-teal-300 hover:text-teal-900"
                          onClick={(event) => {
                            event.stopPropagation();
                            openEdit(campaign);
                          }}
                          type="button"
                        >
                          <Pencil className="size-4" />
                        </button>
                        <button
                          className="rounded-full border border-slate-200 p-2 text-slate-500 transition hover:border-rose-300 hover:text-rose-700"
                          onClick={(event) => {
                            event.stopPropagation();
                            if (
                              window.confirm(
                                `Delete campaign \"${campaign.name}\"?`,
                              )
                            ) {
                              deleteMutation.mutate(campaign.id);
                            }
                          }}
                          type="button"
                        >
                          <Trash2 className="size-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="dashboard-panel flex items-center justify-between gap-4 px-5 py-4">
        <p className="text-sm text-slate-600">
          Page {page} of {pageCount}
        </p>
        <div className="flex gap-3">
          <Button
            isDisabled={page <= 1}
            variant="secondary"
            onPress={() => setPage((current) => Math.max(1, current - 1))}
          >
            Previous
          </Button>
          <Button
            isDisabled={page >= pageCount}
            variant="secondary"
            onPress={() =>
              setPage((current) => Math.min(pageCount, current + 1))
            }
          >
            Next
          </Button>
        </div>
      </div>

      <Dialog
        open={formOpen}
        title={editingCampaign ? "Edit campaign" : "Create campaign"}
        description="Campaign schedules are captured in Bangladesh/Dhaka time. Billable account follows the selected connect-to value."
        onClose={() => {
          setFormOpen(false);
          setEditingCampaign(null);
        }}
        footer={
          <>
            <Button
              type="button"
              variant="secondary"
              onPress={() => {
                setFormOpen(false);
                setEditingCampaign(null);
              }}
            >
              Cancel
            </Button>
            <Button
              isPending={saveMutation.isPending}
              type="submit"
              form="campaign-form"
            >
              {editingCampaign ? "Save changes" : "Create campaign"}
            </Button>
          </>
        }
      >
        <form
          className="grid gap-4 md:grid-cols-2"
          id="campaign-form"
          onSubmit={form.handleSubmit((values) => saveMutation.mutate(values))}
        >
          <label className="space-y-2 md:col-span-2">
            <span className="text-sm font-medium text-slate-700">Name</span>
            <input
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
              {...form.register("name")}
            />
            <span className="text-sm text-rose-700">
              {form.formState.errors.name?.message}
            </span>
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium text-slate-700">Status</span>
            <select
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
              {...form.register("status")}
            >
              {campaignStatuses.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium text-slate-700">Schedule</span>
            <input
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
              type="datetime-local"
              {...form.register("scheduled_at")}
            />
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium text-slate-700">
              Connect to
            </span>
            <select
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
              {...form.register("connect_to")}
            >
              <option value="">Select an account</option>
              {accountOptionsQuery.data?.options.map((option) => (
                <option key={option.connect_to} value={option.connect_to}>
                  {option.label}
                </option>
              ))}
            </select>
            <span className="text-sm text-rose-700">
              {form.formState.errors.connect_to?.message}
            </span>
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium text-slate-700">
              Campaign pace
            </span>
            <input
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
              type="number"
              min={1}
              {...form.register("campaign_pace", { valueAsNumber: true })}
            />
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium text-slate-700">
              Billable account
            </span>
            <input
              className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 outline-none"
              readOnly
              {...form.register("billable_account")}
            />
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium text-slate-700">
              Caller ID
            </span>
            <select
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
              {...form.register("caller_id")}
            >
              <option value="">Select caller ID</option>
              {accountOptionsQuery.data?.options.map((option) => (
                <option
                  key={`${option.connect_to}-${option.caller_id}`}
                  value={option.caller_id}
                >
                  {option.caller_id}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-2 md:col-span-2">
            <span className="text-sm font-medium text-slate-700">
              Description
            </span>
            <textarea
              className="min-h-32 w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
              {...form.register("description")}
            />
          </label>
        </form>
      </Dialog>

      <Dialog
        open={detailOpen && Boolean(selectedCampaign)}
        title={selectedCampaign?.name ?? "Campaign details"}
        description="Monitor campaign state, access the related contacts, and control campaign execution from here."
        onClose={() => setDetailOpen(false)}
        widthClassName="max-w-4xl"
      >
        {selectedCampaign ? (
          <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="data-card">
                <p className="section-heading">Status</p>
                <p className="mt-3 text-xl font-semibold text-slate-950">
                  {selectedCampaign.status}
                </p>
              </div>
              <div className="data-card">
                <p className="section-heading">Ongoing calls</p>
                <p className="mt-3 text-xl font-semibold text-slate-950">
                  {selectedCampaign.ongoing_calls}
                </p>
              </div>
              <div className="data-card">
                <p className="section-heading">Contacts</p>
                <p className="mt-3 text-xl font-semibold text-slate-950">
                  {selectedCampaign.contact_count}
                </p>
              </div>
              <div className="data-card">
                <p className="section-heading">Completed</p>
                <p className="mt-3 text-xl font-semibold text-slate-950">
                  {selectedCampaign.completed_contacts}
                </p>
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
              <div className="dashboard-panel p-5">
                <div className="grid gap-3 text-sm text-slate-600">
                  <div className="flex justify-between gap-4">
                    <span>Connect to</span>
                    <span className="font-medium text-slate-900">
                      {selectedCampaign.connect_to}
                    </span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span>Billable account</span>
                    <span className="font-medium text-slate-900">
                      {selectedCampaign.billable_account}
                    </span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span>Caller ID</span>
                    <span className="font-medium text-slate-900">
                      {selectedCampaign.caller_id}
                    </span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span>Schedule</span>
                    <span className="font-medium text-slate-900">
                      {formatDhakaDateTime(selectedCampaign.scheduled_at)}
                    </span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span>Audio</span>
                    <span className="font-medium text-slate-900">
                      {selectedCampaign.audio?.original_name ?? "Not uploaded"}
                    </span>
                  </div>
                </div>
                <div className="mt-5 flex flex-wrap gap-3">
                  {actionVisibility.canStart ? (
                    <Button
                      onPress={() =>
                        actionMutation.mutate({
                          campaignId: selectedCampaign.id,
                          action: "start",
                        })
                      }
                    >
                      <Play className="size-4" /> Start
                    </Button>
                  ) : null}
                  {actionVisibility.canPause ? (
                    <Button
                      variant="secondary"
                      onPress={() =>
                        actionMutation.mutate({
                          campaignId: selectedCampaign.id,
                          action: "pause",
                        })
                      }
                    >
                      <Pause className="size-4" /> Pause
                    </Button>
                  ) : null}
                  {actionVisibility.canResume ? (
                    <Button
                      variant="secondary"
                      onPress={() =>
                        actionMutation.mutate({
                          campaignId: selectedCampaign.id,
                          action: "resume",
                        })
                      }
                    >
                      <PhoneCall className="size-4" /> Resume
                    </Button>
                  ) : null}
                  {actionVisibility.canRestart ? (
                    <Button
                      variant="secondary"
                      onPress={() =>
                        actionMutation.mutate({
                          campaignId: selectedCampaign.id,
                          action: "restart",
                        })
                      }
                    >
                      <RotateCcw className="size-4" /> Restart
                    </Button>
                  ) : null}
                  {actionVisibility.canStop ? (
                    <Button
                      variant="danger"
                      onPress={() =>
                        actionMutation.mutate({
                          campaignId: selectedCampaign.id,
                          action: "stop",
                        })
                      }
                    >
                      <Square className="size-4" /> Stop
                    </Button>
                  ) : null}
                  <Button
                    variant="outline"
                    onPress={() =>
                      router.push(`/contacts?campaignId=${selectedCampaign.id}`)
                    }
                  >
                    <UserRoundSearch className="size-4" /> View contacts
                  </Button>
                </div>
              </div>

              <div className="dashboard-panel p-5">
                <p className="section-heading">Recent calls</p>
                <div className="mt-4 space-y-3">
                  {callLogQuery.isLoading ? (
                    <TableSkeleton />
                  ) : callLogQuery.data?.results.length ? (
                    callLogQuery.data.results.slice(0, 5).map((call) => (
                      <div
                        key={call.id}
                        className="rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-600"
                      >
                        <div className="flex items-center justify-between gap-4">
                          <span className="font-medium text-slate-900">
                            {call.contact_name || call.destination}
                          </span>
                          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-700">
                            {call.status}
                          </span>
                        </div>
                        <div className="mt-2 flex items-center justify-between gap-4 text-xs text-slate-500">
                          <span>{call.destination}</span>
                          <span>{call.duration}s</span>
                        </div>
                        <p className="mt-2 text-xs text-slate-500">
                          {call.reason || formatDhakaDateTime(call.update_time)}
                        </p>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                      No call activity recorded yet.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </Dialog>
    </div>
  );
}
