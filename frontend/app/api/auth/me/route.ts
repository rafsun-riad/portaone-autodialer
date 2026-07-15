import { NextResponse } from "next/server";

import { fetchBackend } from "@/lib/server-api";

export async function GET() {
  try {
    const backendResponse = await fetchBackend("auth/me/");
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch {
    return NextResponse.json(
      { message: "Unable to load the current session." },
      { status: 401 },
    );
  }
}
