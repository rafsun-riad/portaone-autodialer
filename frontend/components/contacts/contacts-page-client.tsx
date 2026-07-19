"use client";

import { Button } from "@heroui/react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Dialog } from "@/components/ui/dialog";
import { apiRequest } from "@/lib/client-api";
import { useAppStore } from "@/stores/app-store";

type PaginatedResponse<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

type CampaignOption = {
  id: number;
  name: string;
};

type Contact = {
  id: number;
  campaign: number;
  campaign_name: string;
  phone_number: string;
  name: string;
  comments: string;
  status: string;
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

const contactSchema = z.object({
  campaign: z.number().int().positive("Campaign is required."),
  phone_number: z.string().min(8, "Phone number is required."),
  name: z.string().min(2, "Name is required."),
  comments: z.string().optional(),
  status: z.enum(contactStatuses),
});

const bulkSchema = z.object({
  campaign: z.number().int().positive("Campaign is required."),
  file: z.any(),
});

type ContactValues = z.infer<typeof contactSchema>;
type BulkValues = z.infer<typeof bulkSchema>;

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
  const [notice, setNotice] = useState<string | null>(null);

  const form = useForm<ContactValues>({
    resolver: zodResolver(contactSchema),
    defaultValues: {
      campaign: initialCampaignId ? Number(initialCampaignId) : 0,
      phone_number: "",
      name: "",
      comments: "",
      status: "new",
    },
  });

  const bulkForm = useForm<BulkValues>({
    resolver: zodResolver(bulkSchema),
    defaultValues: {
      campaign: initialCampaignId ? Number(initialCampaignId) : 0,
    },
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
    mutationFn: (contactId: number) =>
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

      return apiRequest<{
        created_count: number;
        updated_count: number;
        errors: unknown[];
      }>("/api/backend/contacts/bulk-upload/", {
        method: "POST",
        body: formData,
      });
    },
    onSuccess: (data) => {
      setBulkOpen(false);
      setNotice(
        `Bulk upload complete. Created ${data.created_count} and updated ${data.updated_count} contacts.`,
      );
      queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
    onError: (error) => {
      setNotice(error instanceof Error ? error.message : "Bulk upload failed.");
    },
  });

  const openCreate = () => {
    setEditingContact(null);
    form.reset({
      campaign: filters.campaignId ? Number(filters.campaignId) : 0,
      phone_number: "",
      name: "",
      comments: "",
      status: "new",
    });
    setFormOpen(true);
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
          <Button variant="secondary" onPress={() => setBulkOpen(true)}>
            <FileUp className="size-4" />
            Bulk upload
          </Button>
        </div>
      </div>

      {notice ? (
        <div className="dashboard-inline-notice rounded-2xl px-4 py-3 text-sm text-teal-900">
          {notice}
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
              {...form.register("campaign", { valueAsNumber: true })}
            >
              <option value="0">Select campaign</option>
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
        onClose={() => setBulkOpen(false)}
        footer={
          <>
            <Button
              type="button"
              variant="secondary"
              onPress={() => setBulkOpen(false)}
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
        }
      >
        <form
          className="grid gap-4"
          id="bulk-contact-form"
          onSubmit={bulkForm.handleSubmit((values) =>
            bulkMutation.mutate(values),
          )}
        >
          <label className="space-y-2">
            <span className="text-sm font-medium text-slate-700">Campaign</span>
            <select
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
              {...bulkForm.register("campaign", { valueAsNumber: true })}
            >
              <option value="0">Select campaign</option>
              {campaignsQuery.data?.results.map((campaign) => (
                <option key={campaign.id} value={campaign.id}>
                  {campaign.name}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-2">
            <span className="text-sm font-medium text-slate-700">CSV file</span>
            <input
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none"
              type="file"
              accept=".csv"
              {...bulkForm.register("file")}
            />
          </label>
        </form>
      </Dialog>
    </div>
  );
}
