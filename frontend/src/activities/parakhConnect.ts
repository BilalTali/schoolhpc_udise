import { ApiError } from "../api";

// A screen that needs PARAKH while the app is not connected gets a 409 from the server; this opens the
// connection panel from anywhere (App listens for the event).

export const OPEN_PARAKH_EVENT = "ta:open-parakh";

export const needsParakh = (e: unknown) => e instanceof ApiError && e.status === 409;

export function openParakh() {
  window.dispatchEvent(new Event(OPEN_PARAKH_EVENT));
}
