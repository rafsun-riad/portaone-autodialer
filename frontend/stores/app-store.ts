"use client";

import { create } from "zustand";

export type SessionUser = {
  username: string;
  iCustomer: number | null;
  displayName: string;
  balance: number | null;
  lastSyncedAt: string | null;
};

type ContactFilters = {
  search: string;
  name: string;
  phoneNumber: string;
  campaignId: string;
};

type AppStore = {
  user: SessionUser | null;
  sidebarOpen: boolean;
  campaignSearch: string;
  contactFilters: ContactFilters;
  setUser: (user: SessionUser | null) => void;
  setSidebarOpen: (open: boolean) => void;
  setCampaignSearch: (value: string) => void;
  setContactFilters: (filters: Partial<ContactFilters>) => void;
  resetContactFilters: () => void;
};

const defaultContactFilters: ContactFilters = {
  search: "",
  name: "",
  phoneNumber: "",
  campaignId: "",
};

export const useAppStore = create<AppStore>((set) => ({
  user: null,
  sidebarOpen: false,
  campaignSearch: "",
  contactFilters: defaultContactFilters,
  setUser: (user) => set({ user }),
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  setCampaignSearch: (campaignSearch) => set({ campaignSearch }),
  setContactFilters: (filters) =>
    set((state) => ({
      contactFilters: {
        ...state.contactFilters,
        ...filters,
      },
    })),
  resetContactFilters: () => set({ contactFilters: defaultContactFilters }),
}));
