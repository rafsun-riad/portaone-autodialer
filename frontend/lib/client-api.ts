export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly data: unknown,
  ) {
    super(message);
  }
}

export async function apiRequest<T>(
  path: string,
  init: Omit<RequestInit, "body"> & {
    body?: BodyInit | FormData | Record<string, unknown>;
  } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  let body = init.body as BodyInit | null | undefined;

  if (
    body &&
    !(body instanceof FormData) &&
    !(body instanceof URLSearchParams) &&
    typeof body === "object" &&
    !(body instanceof Blob) &&
    !(body instanceof ArrayBuffer)
  ) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }

  const response = await fetch(path, {
    ...init,
    headers,
    body,
    cache: "no-store",
  });

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const message =
      typeof data === "object" && data !== null
        ? String(
            (data as { message?: string; detail?: string }).message ??
              (data as { detail?: string }).detail ??
              `Request failed with status ${response.status}.`,
          )
        : `Request failed with status ${response.status}.`;

    console.error("API request failed", {
      path,
      status: response.status,
      data,
    });

    throw new ApiError(message, response.status, data);
  }

  return data as T;
}
