import { NextResponse } from "next/server";

import { BACKEND_API_ORIGIN } from "@/lib/env";

export async function POST(request: Request) {
  const payload = await request.json();
  const backendResponse = await fetch(
    `${BACKEND_API_ORIGIN}/api/auth/change-password/`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    },
  );

  const data = await backendResponse.json();
  return NextResponse.json(data, { status: backendResponse.status });
}
