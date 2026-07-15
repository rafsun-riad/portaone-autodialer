"use client";

import { useEffect } from "react";

import { type SessionUser, useAppStore } from "@/stores/app-store";

export function SessionBootstrap({ user }: { user: SessionUser }) {
  const setUser = useAppStore((state) => state.setUser);

  useEffect(() => {
    setUser(user);
  }, [setUser, user]);

  return null;
}
