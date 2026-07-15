import { NextResponse } from "next/server";

import { BACKEND_API_ORIGIN } from "@/lib/env";
import { getStoredSession } from "@/lib/session";

async function proxyRequest(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const session = await getStoredSession();

  if (!session.accessToken || !session.username) {
    return NextResponse.json({ message: "Unauthorized" }, { status: 401 });
  }

  const headers = new Headers();
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${session.accessToken}`);
  headers.set("X-Portal-Username", session.username);

  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("Content-Type", contentType);
  }

  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  const backendResponse = await fetch(
    `${BACKEND_API_ORIGIN}/api/${path.join("/")}/${new URL(request.url).search}`,
    {
      method: request.method,
      headers,
      body,
      cache: "no-store",
    },
  );

  const responseHeaders = new Headers();
  const responseContentType = backendResponse.headers.get("content-type");
  if (responseContentType) {
    responseHeaders.set("Content-Type", responseContentType);
  }
  const disposition = backendResponse.headers.get("content-disposition");
  if (disposition) {
    responseHeaders.set("Content-Disposition", disposition);
  }

  return new NextResponse(await backendResponse.arrayBuffer(), {
    status: backendResponse.status,
    headers: responseHeaders,
  });
}

export {
  proxyRequest as DELETE,
  proxyRequest as GET,
  proxyRequest as PATCH,
  proxyRequest as POST,
  proxyRequest as PUT,
};
