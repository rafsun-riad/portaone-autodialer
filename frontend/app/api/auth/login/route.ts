import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { BACKEND_API_ORIGIN } from "@/lib/env";
import { SESSION_COOKIE_KEYS } from "@/lib/session";

const baseCookieOptions = {
  httpOnly: true,
  sameSite: "lax" as const,
  secure: process.env.NODE_ENV === "production",
  path: "/",
};

function parseCookieExpiry(value?: string | null) {
  if (!value) {
    return undefined;
  }

  const normalized = value.includes("T")
    ? value
    : value.replace(" ", "T") + "+06:00";
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? undefined : parsed;
}

export async function POST(request: Request) {
  const payload = await request.json();
  let backendResponse: Response;

  try {
    backendResponse = await fetch(`${BACKEND_API_ORIGIN}/api/auth/login/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
  } catch (error) {
    return NextResponse.json(
      {
        message:
          error instanceof Error
            ? error.message
            : "Unable to reach the backend login endpoint.",
      },
      { status: 502 },
    );
  }

  const rawBody = await backendResponse.text();
  let data: Record<string, unknown> | null = null;

  if (rawBody) {
    try {
      data = JSON.parse(rawBody) as Record<string, unknown>;
    } catch {
      data = { message: rawBody.slice(0, 500) };
    }
  }

  if (!backendResponse.ok) {
    return NextResponse.json(
      data ?? {
        message: `Backend login failed with status ${backendResponse.status}.`,
      },
      { status: backendResponse.status },
    );
  }

  const cookieStore = await cookies();
  const auth = (data?.auth ?? {}) as Record<string, unknown>;
  const expires = parseCookieExpiry(
    typeof auth.expires_at === "string" ? auth.expires_at : null,
  );

  cookieStore.set(
    SESSION_COOKIE_KEYS.accessToken,
    String(auth.access_token ?? ""),
    {
      ...baseCookieOptions,
      expires,
    },
  );
  cookieStore.set(
    SESSION_COOKIE_KEYS.refreshToken,
    String(auth.refresh_token ?? ""),
    {
      ...baseCookieOptions,
      expires,
    },
  );
  cookieStore.set(
    SESSION_COOKIE_KEYS.sessionId,
    String(auth.session_id ?? ""),
    {
      ...baseCookieOptions,
      expires,
    },
  );
  cookieStore.set(SESSION_COOKIE_KEYS.username, payload.username, {
    ...baseCookieOptions,
    expires,
  });
  cookieStore.set(
    SESSION_COOKIE_KEYS.expiresAt,
    String(auth.expires_at ?? ""),
    {
      ...baseCookieOptions,
      expires,
    },
  );

  return NextResponse.json({ profile: data?.profile ?? null });
}
