import { apiFetch } from "./api";
import type { Api } from "./api";

/** Downloads a file the server makes; the server's reason when it cannot (null when downloaded). */
export async function downloadSheet(api: Api, path: string, name: string): Promise<string | null> {
  const res = await apiFetch(path, {}, api.base);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return typeof body.detail === "string" ? body.detail : `The file could not be made (error ${res.status}).`;
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
  return null;
}
