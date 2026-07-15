"use client";

import { Button } from "@heroui/react";
import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiRequest } from "@/lib/client-api";

export function LogoutButton() {
  const router = useRouter();
  const [isPending, setIsPending] = useState(false);

  return (
    <Button
      className="w-full justify-start"
      isPending={isPending}
      variant="secondary"
      onPress={async () => {
        setIsPending(true);
        try {
          await apiRequest<{ success: true }>("/api/auth/logout", {
            method: "POST",
          });
          router.push("/");
          router.refresh();
        } finally {
          setIsPending(false);
        }
      }}
    >
      <LogOut className="size-4" />
      Sign out
    </Button>
  );
}
