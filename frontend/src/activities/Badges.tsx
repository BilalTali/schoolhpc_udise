import { AlertCircle } from "lucide-react";
import { SOURCE_LABEL } from "./types";
import type { Activity, Source } from "./types";

// Every badge says what it means in words; colour is only a second hint.

// Where an activity belongs: its subject and its grade (it is offered only there).
export function PlaceBadges({ activity }: { activity: Pick<Activity, "subject_names" | "grade_name"> }) {
  return (
    <span className="lib-place">
      {activity.subject_names.map((s) => <span key={s} className="lib-badge lib-badge-subject">{s}</span>)}
      {activity.grade_name
        ? <span className="lib-badge">{activity.grade_name}</span>
        : <span className="lib-badge lib-badge-warn" title="Not offered to any student until its grade is set">
            <AlertCircle size={12} aria-hidden="true" /> No grade set
          </span>}
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
