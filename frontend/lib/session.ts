import "server-only";

import { cookies } from "next/headers";

export const SESSION_COOKIE_KEYS = {
  accessToken: "portaone_access_token",
  refreshToken: "portaone_refresh_token",
  sessionId: "portaone_session_id",
  username: "portaone_username",
  expiresAt: "portaone_expires_at",
} as const;

export type StoredSession = {
  accessToken: string | null;
  refreshToken: string | null;
  sessionId: string | null;
  username: string | null;
  expiresAt: string | null;
};

export async function getStoredSession(): Promise<StoredSession> {
  const cookieStore = await cookies();

  return {
    accessToken:
      cookieStore.get(SESSION_COOKIE_KEYS.accessToken)?.value ?? null,
    refreshToken:
      cookieStore.get(SESSION_COOKIE_KEYS.refreshToken)?.value ?? null,
    sessionId: cookieStore.get(SESSION_COOKIE_KEYS.sessionId)?.value ?? null,
    username: cookieStore.get(SESSION_COOKIE_KEYS.username)?.value ?? null,
    expiresAt: cookieStore.get(SESSION_COOKIE_KEYS.expiresAt)?.value ?? null,
  };
}
