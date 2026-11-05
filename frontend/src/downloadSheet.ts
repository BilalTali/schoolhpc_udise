import { apiFetch } from "./api";
import type { Api } from "./api";

/** Saves a file to the computer. The link is put on the page and freed only after the browser has taken the file:
 *  freeing it at once makes Firefox and Safari save an empty or broken file. */
export function saveBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  window.setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 60_000);
}

/** Downloads a file the server makes; the server's reason when it cannot (null when downloaded). */
export async function downloadSheet(api: Api, path: string, name: string): Promise<string | null> {
  const res = await apiFetch(path, {}, api.base);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return typeof body.detail === "string" ? body.detail : `The file could not be made (error ${res.status}).`;
  }
  const blob = await res.blob();
  if (!blob.size) return "The server sent an empty file. Fetch the students again, then download.";
  saveBlob(blob, name);
  return null;
}
