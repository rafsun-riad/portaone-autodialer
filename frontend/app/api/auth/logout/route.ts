import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { SESSION_COOKIE_KEYS } from "@/lib/session";

export async function POST() {
  const cookieStore = await cookies();

  for (const key of Object.values(SESSION_COOKIE_KEYS)) {
    cookieStore.delete(key);
  }

  return NextResponse.json({ success: true });
}
