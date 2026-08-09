"use client";

import { Button } from "@heroui/react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Dialog } from "@/components/ui/dialog";
import { ApiError, apiRequest } from "@/lib/client-api";
import { useAppStore } from "@/stores/app-store";

type PaginatedResponse<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

type EntityId = string;

type CampaignOption = {
  id: EntityId;
  name: string;
};

type Contact = {
  id: EntityId;
  campaign: EntityId;
  campaign_name: string;
  phone_number: string;
  name: string;
  comments: string;
  status: string;
};

type ContactImportJob = {
  id: EntityId;
  campaign: EntityId;
  campaign_name: string;
  status: string;
  original_filename: string;
  total_rows: number;
  processed_rows: number;
  created_count: number;
  failed_count: number;
  cancel_requested: boolean;
  error_message: string;
  started_at: string | null;
  completed_at: string | null;
  progress_percent: number;
};

type ContactImportFailure = {
  id: EntityId;
  row_number: number;
  phone_number: string;
  failure_reason: string;
  row_data: Record<string, unknown>;
  created_at: string;
};

type ActiveContactImportJobResponse = {
  job: ContactImportJob | null;
};

const contactStatuses = [
  "new",
  "active",
  "queued",
  "called",
  "failed",
  "paused",
  "invalid",
] as const;

const campaignIdSchema = z.string().min(1, "Campaign is required.");

const contactSchema = z.object({
  campaign: campaignIdSchema,
  phone_number: z.string().min(8, "Phone number is required."),
  name: z.string().min(2, "Name is required."),
  comments: z.string().optional(),
  status: z.enum(contactStatuses),
});

const bulkSchema = z.object({
  campaign: campaignIdSchema,
  file: z.any(),
});

type ContactValues = z.infer<typeof contactSchema>;
type BulkValues = z.infer<typeof bulkSchema>;

const terminalImportStatuses = ["completed", "failed", "canceled"] as const;

function ContactSkeleton() {
  return (
    <div className="space-y-3">
      <div className="skeleton-block h-14" />
      <div className="skeleton-block h-14" />
      <div className="skeleton-block h-14" />
    </div>
  );
}

export function ContactsPageClient({
  initialCampaignId,
}: {
  initialCampaignId: string;
}) {
  const queryClient = useQueryClient();
  const filters = useAppStore((state) => state.contactFilters);
  const setContactFilters = useAppStore((state) => state.setContactFilters);
  const [page, setPage] = useState(1);
  const [formOpen, setFormOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [editingContact, setEditingContact] = useState<Contact | null>(null);
  const [activeImportJobId, setActiveImportJobId] = useState<string | null>(
    null,
  );
  const [failurePage, setFailurePage] = useState(1);
  const [notice, setNotice] = useState<string | null>(null);
  const reportedTerminalImportJobIdRef = useRef<string | null>(null);

  const form = useForm<ContactValues>({
    resolver: zodResolver(contactSchema),
    defaultValues: {
      campaign: initialCampaignId,
      phone_number: "",
      name: "",
      comments: "",
      status: "new",
    },
  });

  const bulkForm = useForm<BulkValues>({
    resolver: zodResolver(bulkSchema),
    defaultValues: {
      campaign: initialCampaignId,
    },
  });

  const selectedBulkCampaignId = useWatch({
    control: bulkForm.control,
    name: "campaign",
  });

  useEffect(() => {
    if (initialCampaignId && !filters.campaignId) {
      setContactFilters({ campaignId: initialCampaignId });
    }
  }, [filters.campaignId, initialCampaignId, setContactFilters]);

  const campaignsQuery = useQuery({
    queryKey: ["contact-campaigns"],
    queryFn: () =>
      apiRequest<PaginatedResponse<CampaignOption>>(
        "/api/backend/campaigns/?page_size=200",
      ),
  });

  const contactsQuery = useQuery({
    queryKey: ["contacts", page, filters],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page) });
      if (filters.search) params.set("search", filters.search);
      if (filters.name) params.set("name", filters.name);
      if (filters.phoneNumber) params.set("phone_number", filters.phoneNumber);
      if (filters.campaignId) params.set("campaign", filters.campaignId);

      return apiRequest<PaginatedResponse<Contact>>(
        `/api/backend/contacts/?${params.toString()}`,
      );
    },
  });

  const saveMutation = useMutation({
    mutationFn: (values: ContactValues) => {
      if (editingContact) {
        return apiRequest<Contact>(
          `/api/backend/contacts/${editingContact.id}/`,
          {
            method: "PATCH",
            body: values,
          },
        );
      }

      return apiRequest<Contact>("/api/backend/contacts/", {
        method: "POST",
        body: values,
      });
    },
    onSuccess: () => {
      setFormOpen(false);
      setEditingContact(null);
      setNotice(editingContact ? "Contact updated." : "Contact created.");
      queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
    onError: (error) => {
      setNotice(
        error instanceof Error ? error.message : "Unable to save the contact.",
      );
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (contactId: EntityId) =>
      apiRequest<void>(`/api/backend/contacts/${contactId}/`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      setNotice("Contact deleted.");
      queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
  });

  const bulkMutation = useMutation({
    mutationFn: (values: BulkValues) => {
      const formData = new FormData();
      formData.append("campaign", String(values.campaign));
      const fileInput = values.file?.[0] as File | undefined;
      if (!fileInput) {
        throw new Error("Select a CSV file to upload.");
      }
      formData.append("file", fileInput);

      return apiRequest<ContactImportJob>(
        "/api/backend/contacts/bulk-upload/",
        {
          method: "POST",
          body: formData,
        },
      );
    },
    onSuccess: (job) => {
      setActiveImportJobId(job.id);
      setFailurePage(1);
      reportedTerminalImportJobIdRef.current = null;
      setNotice(
        "Contact import started. Progress will continue in the background.",
      );
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        const activeJob = (error.data as { job?: ContactImportJob } | null)
          ?.job;
        if (activeJob) {
          setActiveImportJobId(activeJob.id);
          setFailurePage(1);
          setNotice(
            "An active import already exists for this campaign. Resuming it now.",
          );
          return;
        }
      }
      setNotice(error instanceof Error ? error.message : "Bulk upload failed.");
    },
  });

  const activeImportJobQuery = useQuery({
    queryKey: ["contact-import-job-active", bulkOpen, selectedBulkCampaignId],
    enabled: bulkOpen && Boolean(selectedBulkCampaignId) && !activeImportJobId,
    queryFn: () =>
      apiRequest<ActiveContactImportJobResponse>(
        `/api/backend/contacts/import-jobs/active/?campaign=${selectedBulkCampaignId}`,
      ),
  });

  const effectiveImportJobId =
    activeImportJobId ?? activeImportJobQuery.data?.job?.id ?? null;

  const importJobQuery = useQuery({
    queryKey: ["contact-import-job", effectiveImportJobId],
    enabled: Boolean(effectiveImportJobId),
    queryFn: () =>
      apiRequest<ContactImportJob>(
        `/api/backend/contacts/import-jobs/${effectiveImportJobId}/`,
      ),
    refetchInterval: (query) => {
      const currentJob = query.state.data;
      if (!currentJob) {
        return 2000;
      }
      return terminalImportStatuses.includes(
        currentJob.status as (typeof terminalImportStatuses)[number],
      )
        ? false
        : 2000;
    },
    refetchIntervalInBackground: true,
  });

  const activeImportJob =
    importJobQuery.data ?? activeImportJobQuery.data?.job ?? null;

  const importFailureQuery = useQuery({
    queryKey: [
      "contact-import-job-failures",
      effectiveImportJobId,
      failurePage,
      activeImportJob?.failed_count,
    ],
    enabled:
      Boolean(effectiveImportJobId) && (activeImportJob?.failed_count ?? 0) > 0,
    queryFn: () =>
      apiRequest<PaginatedResponse<ContactImportFailure>>(
        `/api/backend/contacts/import-jobs/${effectiveImportJobId}/failures/?page=${failurePage}&page_size=25`,
      ),
  });

  const cancelImportMutation = useMutation({
    mutationFn: (jobId: EntityId) =>
      apiRequest<ContactImportJob>(
        `/api/backend/contacts/import-jobs/${jobId}/cancel/`,
        {
          method: "POST",
        },
      ),
    onSuccess: () => {
      setNotice(
        "Cancellation requested. The current batch will finish before the import stops.",
      );
      if (effectiveImportJobId) {
        queryClient.invalidateQueries({
          queryKey: ["contact-import-job", effectiveImportJobId],
        });
      }
    },
    onError: (error) => {
      setNotice(
        error instanceof Error ? error.message : "Unable to cancel the import.",
      );
    },
  });

  useEffect(() => {
    if (!activeImportJob) {
      return;
    }
    if (
      !terminalImportStatuses.includes(
        activeImportJob.status as (typeof terminalImportStatuses)[number],
      )
    ) {
      return;
    }
    if (reportedTerminalImportJobIdRef.current === activeImportJob.id) {
      return;
    }

    reportedTerminalImportJobIdRef.current = activeImportJob.id;
    queryClient.invalidateQueries({ queryKey: ["contacts"] });
  }, [activeImportJob, queryClient]);

  const openCreate = () => {
    setEditingContact(null);
    form.reset({
      campaign: filters.campaignId,
      phone_number: "",
      name: "",
      comments: "",
      status: "new",
    });
    setFormOpen(true);
  };

  const openBulkUpload = () => {
    setFailurePage(1);
    setActiveImportJobId(null);
    bulkForm.reset({
      campaign: filters.campaignId || initialCampaignId,
      file: undefined,
    });
    setBulkOpen(true);
  };

  const closeBulkUpload = () => {
    setBulkOpen(false);
    setActiveImportJobId(null);
    setFailurePage(1);
  };

  const resetBulkImportView = () => {
    setActiveImportJobId(null);
    setFailurePage(1);
    reportedTerminalImportJobIdRef.current = null;
    bulkForm.reset({
      campaign:
        activeImportJob?.campaign || filters.campaignId || initialCampaignId,
      file: undefined,
    });
  };

  const openEdit = (contact: Contact) => {
    setEditingContact(contact);
    form.reset({
      campaign: contact.campaign,
      phone_number: contact.phone_number,
      name: contact.name,
      comments: contact.comments,
      status: contact.status as ContactValues["status"],
    });
    setFormOpen(true);
  };

  const pageCount = Math.max(
    1,
    Math.ceil((contactsQuery.data?.count ?? 0) / 100),
  );
  const importFailurePageCount = Math.max(
    1,
    Math.ceil((importFailureQuery.data?.count ?? 0) / 25),
  );
  const importIsTerminal = activeImportJob
    ? terminalImportStatuses.includes(
        activeImportJob.status as (typeof terminalImportStatuses)[number],
      )
    : false;
  const importIsRunning = Boolean(activeImportJob && !importIsTerminal);
  const importProgressPercent =
    activeImportJob?.total_rows && activeImportJob.total_rows > 0
      ? activeImportJob.progress_percent
      : 0;
  const importTerminalNotice =
    activeImportJob && importIsTerminal
      ? activeImportJob.status === "completed"
        ? `Contact import complete. Added ${activeImportJob.created_count} contacts and failed ${activeImportJob.failed_count} rows.`
        : activeImportJob.status === "canceled"
          ? `Contact import canceled after processing ${activeImportJob.processed_rows} rows.`
          : activeImportJob.error_message ||
            `Contact import failed after processing ${activeImportJob.processed_rows} rows.`
      : null;
  const visibleNotice = notice || importTerminalNotice;

  return (
    <div className="space-y-6">
      <div className="dashboard-panel flex flex-col gap-4 p-6 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="section-heading">Contact registry</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-950">
            Campaign contacts
          </h2>
          <p className="mt-2 text-sm leading-7 text-slate-600">
            Create contacts one by one, upload them in bulk, and keep the phone
            list aligned with campaign ownership.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button onPress={openCreate}>
            <Plus className="size-4" />
            Add contact
          </Button>
          <Button variant="secondary" onPress={openBulkUpload}>
            <FileUp className="size-4" />
            Bulk upload
          </Button>
        </div>
      </div>

      {visibleNotice ? (
        <div className="dashboard-inline-notice rounded-2xl px-4 py-3 text-sm text-teal-900">
          {visibleNotice}
        </div>
      ) : null}

      <section className="dashboard-panel grid gap-4 p-5 lg:grid-cols-4">
        <div className="dashboard-input-shell flex items-center gap-3 px-4 py-3 lg:col-span-2 rounded-2xl">
          <Search className="size-4 text-slate-400" />
          <input
            className="w-full bg-transparent outline-none"
            placeholder="Search by name, phone, or campaign"
            value={filters.search}
            onChange={(event) => {
              setContactFilters({ search: event.target.value });
              setPage(1);
            }}
          />
        </div>
        <input
          className="dashboard-input-shell rounded-2xl px-4 py-3 outline-none"
          placeholder="Filter by contact name"
          value={filters.name}
          onChange={(event) => {
            setContactFilters({ name: event.target.value });
            setPage(1);
          }}
        />
        <input
          className="dashboard-input-shell rounded-2xl px-4 py-3 outline-none"
          placeholder="Filter by phone"
          value={filters.phoneNumber}
          onChange={(event) => {
            setContactFilters({ phoneNumber: event.target.value });
            setPage(1);
          }}
        />
      </section>

      <section className="dashboard-panel grid gap-4 p-5 lg:grid-cols-[1fr_auto]">
        <select
          className="dashboard-input-shell rounded-2xl px-4 py-3 outline-none"
          value={filters.campaignId}
          onChange={(event) => {
            setContactFilters({ campaignId: event.target.value });
            setPage(1);
          }}
        >
          <option value="">All campaigns</option>
          {campaignsQuery.data?.results.map((campaign) => (
            <option key={campaign.id} value={campaign.id}>
              {campaign.name}
            </option>
          ))}
        </select>
        <a
          className="dashboard-muted-chip inline-flex items-center justify-center rounded-2xl px-4 py-3 text-sm font-medium text-slate-700 transition hover:border-teal-200 hover:text-teal-900"
          download
          href="/contact-import-template.csv"
        >
          Download demo CSV
        </a>
      </section>

      <section className="dashboard-panel overflow-hidden">
        {contactsQuery.isLoading ? (
          <div className="p-5">
            <ContactSkeleton />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-5 py-4 font-medium">Name</th>
                  <th className="px-5 py-4 font-medium">Phone</th>
                  <th className="px-5 py-4 font-medium">Campaign</th>
                  <th className="px-5 py-4 font-medium">Status</th>
                  <th className="px-5 py-4 font-medium">Comments</th>
                  <th className="px-5 py-4 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {contactsQuery.data?.results.map((contact) => (
                  <tr key={contact.id} className="transition hover:bg-slate-50">
                    <td className="px-5 py-4 font-medium text-slate-900">
                      {contact.name}
                    </td>
                    <td className="px-5 py-4 text-slate-700">
                      {contact.phone_number}
                    </td>
                    <td className="px-5 py-4 text-slate-700">
                      {contact.campaign_name}
                    </td>
                    <td className="px-5 py-4 text-slate-700">
                      {contact.status}
                    </td>
                    <td className="px-5 py-4 text-slate-500">
                      {contact.comments || "-"}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex justify-end gap-2">
                        <button
                          className="rounded-full border border-slate-200 p-2 text-slate-500 transition hover:border-teal-300 hover:text-teal-900"
                          onClick={() => openEdit(contact)}
                          type="button"
                        >
                          <Pencil className="size-4" />
                        </button>
                        <button
                          className="rounded-full border border-slate-200 p-2 text-slate-500 transition hover:border-rose-300 hover:text-rose-700"
                          onClick={() => {
                            if (
                              window.confirm(
                                `Delete contact \"${contact.name}\"?`,
                              )
                            ) {
                              deleteMutation.mutate(contact.id);
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
        title={editingContact ? "Edit contact" : "Add contact"}
        description="Phone numbers are normalized with the 88 prefix before they are saved."
        onClose={() => {
          setFormOpen(false);
          setEditingContact(null);
        }}
        footer={
          <>
            <Button
              type="button"
              variant="secondary"
              onPress={() => setFormOpen(false)}
            >
              Cancel
            </Button>
            <Button
              isPending={saveMutation.isPending}
              type="submit"
              form="contact-form"
            >
              {editingContact ? "Save contact" : "Create contact"}
            </Button>
          </>
        }
      >
        <form
          className="grid gap-4 md:grid-cols-2"
          id="contact-form"
          onSubmit={form.handleSubmit((values) => saveMutation.mutate(values))}
        >
          <label className="space-y-2 md:col-span-2">
            <span className="text-sm font-medium text-slate-700">Campaign</span>
            <select
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
              {...form.register("campaign")}
            >
              <option value="">Select campaign</option>
              {campaignsQuery.data?.results.map((campaign) => (
                <option key={campaign.id} value={campaign.id}>
                  {campaign.name}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-2">
            <span className="text-sm font-medium text-slate-700">
              Phone number
            </span>
            <input
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
              {...form.register("phone_number")}
            />
          </label>
          <label className="space-y-2">
            <span className="text-sm font-medium text-slate-700">Status</span>
            <select
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
              {...form.register("status")}
            >
              {contactStatuses.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-2 md:col-span-2">
            <span className="text-sm font-medium text-slate-700">Name</span>
            <input
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
              {...form.register("name")}
            />
          </label>
          <label className="space-y-2 md:col-span-2">
            <span className="text-sm font-medium text-slate-700">Comments</span>
            <textarea
              className="min-h-28 w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
              {...form.register("comments")}
            />
          </label>
        </form>
      </Dialog>

      <Dialog
        open={bulkOpen}
        title="Bulk upload contacts"
        description="Select a campaign, then upload a CSV file using the demo template as your reference."
        onClose={closeBulkUpload}
        widthClassName="max-w-4xl"
        footer={
          activeImportJob ? (
            <>
              <Button
                type="button"
                variant="secondary"
                onPress={closeBulkUpload}
              >
                Close
              </Button>
              {importIsRunning ? (
                <Button
                  type="button"
                  isDisabled={
                    activeImportJob.cancel_requested ||
                    cancelImportMutation.isPending
                  }
                  isPending={cancelImportMutation.isPending}
                  onPress={() =>
                    cancelImportMutation.mutate(activeImportJob.id)
                  }
                >
                  {activeImportJob.cancel_requested
                    ? "Cancellation queued"
                    : "Cancel import"}
                </Button>
              ) : (
                <Button type="button" onPress={resetBulkImportView}>
                  Start another import
                </Button>
              )}
            </>
          ) : (
            <>
              <Button
                type="button"
                variant="secondary"
                onPress={closeBulkUpload}
              >
                Cancel
              </Button>
              <Button
                isPending={bulkMutation.isPending}
                type="submit"
                form="bulk-contact-form"
              >
                Upload CSV
              </Button>
            </>
          )
        }
      >
        {activeImportJob ? (
          <div className="space-y-5">
            <section className="rounded-[1.75rem] border border-slate-200 bg-slate-50 p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">
                    Import progress
                  </p>
                  <h4 className="mt-2 text-xl font-semibold text-slate-950">
                    {activeImportJob.original_filename || "contacts.csv"}
                  </h4>
                  <p className="mt-2 text-sm leading-7 text-slate-600">
                    {activeImportJob.status === "preparing"
                      ? "Scanning the CSV to calculate total rows before batch inserts begin."
                      : activeImportJob.status === "processing"
                        ? "Processing contacts in 1000-row batches. Duplicates are reported as failures instead of updates."
                        : activeImportJob.status === "completed"
                          ? "Import finished. Review the summary and failed rows below."
                          : activeImportJob.status === "canceled"
                            ? "Import stopped after the current batch completed."
                            : "Import stopped unexpectedly. Review the error details and failed rows below."}
                  </p>
                </div>
                <div className="inline-flex rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium capitalize text-slate-700">
                  {activeImportJob.cancel_requested && importIsRunning
                    ? "Cancel requested"
                    : activeImportJob.status}
                </div>
              </div>

              <div className="mt-5 overflow-hidden rounded-full bg-slate-200">
                {activeImportJob.total_rows > 0 ? (
                  <div
                    className="h-3 rounded-full bg-teal-500 transition-[width] duration-500"
                    style={{ width: `${importProgressPercent}%` }}
                  />
                ) : (
                  <div className="h-3 w-1/3 rounded-full bg-teal-400 animate-pulse" />
                )}
              </div>

              <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-600">
                <span>
                  {activeImportJob.total_rows > 0
                    ? `${activeImportJob.processed_rows} of ${activeImportJob.total_rows} rows processed`
                    : `${activeImportJob.processed_rows} rows processed while the file scan completes`}
                </span>
                <span>{importProgressPercent}% complete</span>
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-3">
                <div className="rounded-3xl border border-slate-200 bg-white px-4 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">
                    Added
                  </p>
                  <p className="mt-3 text-2xl font-semibold text-slate-950">
                    {activeImportJob.created_count}
                  </p>
                </div>
                <div className="rounded-3xl border border-slate-200 bg-white px-4 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">
                    Failed
                  </p>
                  <p className="mt-3 text-2xl font-semibold text-rose-700">
                    {activeImportJob.failed_count}
                  </p>
                </div>
                <div className="rounded-3xl border border-slate-200 bg-white px-4 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">
                    Campaign
                  </p>
                  <p className="mt-3 text-base font-semibold text-slate-950">
                    {activeImportJob.campaign_name}
                  </p>
                </div>
              </div>

              {activeImportJob.error_message ? (
                <div className="mt-5 rounded-3xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
                  {activeImportJob.error_message}
                </div>
              ) : null}
            </section>

            {activeImportJob.failed_count > 0 ? (
              <section className="rounded-[1.75rem] border border-slate-900 bg-slate-950 p-5 text-slate-100">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-white">
                      Failed rows
                    </p>
                    <p className="text-xs uppercase tracking-[0.3em] text-slate-400">
                      row number and failure reason
                    </p>
                  </div>
                  <div className="text-sm text-slate-300">
                    {activeImportJob.failed_count} failed rows recorded
                  </div>
                </div>

                {importFailureQuery.isLoading ? (
                  <div className="mt-4 rounded-3xl border border-white/10 bg-white/5 px-4 py-6 text-sm text-slate-300">
                    Loading failed rows...
                  </div>
                ) : (
                  <>
                    <div className="mt-4 max-h-80 space-y-3 overflow-y-auto font-mono text-xs leading-6">
                      {importFailureQuery.data?.results.map((failure) => (
                        <div
                          key={failure.id}
                          className="rounded-3xl border border-white/10 bg-white/5 px-4 py-3"
                        >
                          <p className="text-rose-300">
                            row {failure.row_number}
                            {failure.phone_number
                              ? ` | ${failure.phone_number}`
                              : ""}
                          </p>
                          <p className="mt-1 whitespace-pre-wrap text-slate-200">
                            {failure.failure_reason}
                          </p>
                        </div>
                      ))}
                    </div>

                    <div className="mt-4 flex items-center justify-between gap-3 text-sm text-slate-300">
                      <span>
                        Page {failurePage} of {importFailurePageCount}
                      </span>
                      <div className="flex gap-3">
                        <Button
                          isDisabled={failurePage <= 1}
                          variant="secondary"
                          onPress={() =>
                            setFailurePage((current) =>
                              Math.max(1, current - 1),
                            )
                          }
                        >
                          Previous
                        </Button>
                        <Button
                          isDisabled={failurePage >= importFailurePageCount}
                          variant="secondary"
                          onPress={() =>
                            setFailurePage((current) =>
                              Math.min(importFailurePageCount, current + 1),
                            )
                          }
                        >
                          Next
                        </Button>
                      </div>
                    </div>
                  </>
                )}
              </section>
            ) : null}
          </div>
        ) : (
          <form
            className="grid gap-4"
            id="bulk-contact-form"
            onSubmit={bulkForm.handleSubmit((values) =>
              bulkMutation.mutate(values),
            )}
          >
            {activeImportJobQuery.isLoading ? (
              <div className="rounded-3xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                Checking whether this campaign already has a running import...
              </div>
            ) : null}
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">
                Campaign
              </span>
              <select
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
                {...bulkForm.register("campaign")}
              >
                <option value="">Select campaign</option>
                {campaignsQuery.data?.results.map((campaign) => (
                  <option key={campaign.id} value={campaign.id}>
                    {campaign.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">
                CSV file
              </span>
              <input
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
                type="file"
                accept=".csv"
                {...bulkForm.register("file")}
              />
            </label>
          </form>
        )}
      </Dialog>
    </div>
  );
}
