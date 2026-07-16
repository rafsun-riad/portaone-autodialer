import { NextResponse } from "next/server";

import { BACKEND_API_ORIGIN } from "@/lib/env";

async function proxyMedia(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const backendResponse = await fetch(
    `${BACKEND_API_ORIGIN}/media/${path.join("/")}${new URL(request.url).search}`,
    {
      method: request.method,
      headers: {
        Accept: request.headers.get("accept") ?? "*/*",
        Range: request.headers.get("range") ?? "",
      },
      cache: "no-store",
    },
  );

  const responseHeaders = new Headers();
  const contentType = backendResponse.headers.get("content-type");
  const contentLength = backendResponse.headers.get("content-length");
  const contentRange = backendResponse.headers.get("content-range");
  const acceptRanges = backendResponse.headers.get("accept-ranges");
  const disposition = backendResponse.headers.get("content-disposition");

  if (contentType) {
    responseHeaders.set("Content-Type", contentType);
  }
  if (contentLength) {
    responseHeaders.set("Content-Length", contentLength);
  }
  if (contentRange) {
    responseHeaders.set("Content-Range", contentRange);
  }
  if (acceptRanges) {
    responseHeaders.set("Accept-Ranges", acceptRanges);
  }
  if (disposition) {
    responseHeaders.set("Content-Disposition", disposition);
  }

  return new NextResponse(await backendResponse.arrayBuffer(), {
    status: backendResponse.status,
    headers: responseHeaders,
  });
}

export { proxyMedia as GET, proxyMedia as HEAD };
