import { AlertCircle, CheckCircle2 } from "lucide-react";
import { SOURCE_LABEL } from "./types";
import type { Activity, Source } from "./types";

// Every badge says what it means in words; colour is only a second hint.

export function CoverageBadge({ activity }: { activity: Pick<Activity, "covers_all" | "missing_subjects"> }) {
  if (activity.covers_all) {
    return <span className="lib-badge lib-badge-ok"><CheckCircle2 size={12} aria-hidden="true" /> Covers all subjects</span>;
  }
  const missing = activity.missing_subjects;
  const shown = missing.length > 3 ? `${missing.slice(0, 3).join(", ")} +${missing.length - 3} more` : missing.join(", ");
  return (
    <span className="lib-badge lib-badge-warn" title={`Missing: ${missing.join(", ")}`}>
      <AlertCircle size={12} aria-hidden="true" /> Missing: {shown}
    </span>
  );
}

export function SourceBadge({ source }: { source: Source }) {
  return <span className={`lib-badge lib-badge-src-${source}`}>{SOURCE_LABEL[source]}</span>;
}

export function StateBadges({ activity }: { activity: Activity }) {
  return (
    <>
      {activity.is_default && <span className="lib-badge lib-badge-default">Default</span>}
      {activity.edited && <span className="lib-badge lib-badge-edited">Changed</span>}
      {activity.upstream_status === "removed" && <span className="lib-badge lib-badge-bad">No longer on PARAKH</span>}
      {!activity.portal_active && activity.upstream_status !== "removed" && <span className="lib-badge lib-badge-bad">Turned off on PARAKH</span>}
      {activity.has_pictures && <span className="lib-badge">Has pictures</span>}
      {activity.source === "local" && activity.share_state && (
        <span className="lib-badge">{{ private: "Only me", school: "My school", community: "Shared – waiting for check",
                                       community_ok: "Shared with other schools" }[activity.share_state]}</span>
      )}
    </>
  );
}
