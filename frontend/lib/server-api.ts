import "server-only";

import { BACKEND_API_ORIGIN } from "@/lib/env";
import { getStoredSession } from "@/lib/session";

export async function fetchBackend(
  path: string,
  init: RequestInit = {},
  requireAuth = true,
) {
  const session = await getStoredSession();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  if (requireAuth) {
    if (!session.accessToken || !session.username) {
      throw new Error("Missing authenticated session.");
    }

    headers.set("Authorization", `Bearer ${session.accessToken}`);
    headers.set("X-Portal-Username", session.username);
  }

  return fetch(`${BACKEND_API_ORIGIN}/api/${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}

export async function fetchBackendJson<T>(
  path: string,
  init: RequestInit = {},
  requireAuth = true,
): Promise<T> {
  const response = await fetchBackend(path, init, requireAuth);
  const text = await response.text();
  const data = text ? (JSON.parse(text) as T) : (null as T);

  if (!response.ok) {
    const message =
      typeof data === "object" && data !== null && "message" in data
        ? String((data as { message?: string }).message)
        : `Backend request failed with status ${response.status}.`;
    throw new Error(message);
  }

  return data;
}
