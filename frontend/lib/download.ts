export async function downloadFile(path: string, fallbackFileName: string) {
  const response = await fetch(path, {
    method: "GET",
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`;
    try {
      const data = (await response.json()) as {
        message?: string;
        detail?: string;
      };
      message = String(data.message ?? data.detail ?? message);
    } catch {
      // Ignore JSON parsing errors for binary or empty error bodies.
    }
    throw new Error(message);
  }

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const matchedFileName = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  const fileName = matchedFileName || fallbackFileName;
  const downloadUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = downloadUrl;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(downloadUrl);
}
