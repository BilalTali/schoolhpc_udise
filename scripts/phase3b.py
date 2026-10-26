"""
Phase 3b, stage 1: READ ONLY. Uses the PARAKH session the teacher opened in the web app (typed captcha);
never logs in by itself. Only GET requests can be sent: any other request raises before it leaves.

    python scripts/phase3b.py preview --teacher <app teacher id> --stage Preparatory --student <PARAKH id>
    python scripts/phase3b.py restore-preview --teacher <id> --stage Preparatory --student <id> [--snapshot <file>]

preview          fetches only that student, takes a snapshot, prints what PARAKH holds (names masked)
restore-preview  compares a snapshot with what PARAKH holds now: what a restore would put back
Output carries IDs only; names (student, guardian, peers) are shown as "(name, N letters)".
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal  # noqa: E402
from backend.hpc import sync  # noqa: E402
from backend.hpc.portal import Portal, PortalError, stage_code  # noqa: E402
from backend.hpc.stages import activity_grid, get_stage  # noqa: E402
from backend.hpc.stages.common import Lookups  # noqa: E402
from backend.models.entities import Teacher  # noqa: E402
from backend.services import hpc_sessions, snapshots  # noqa: E402

NAME_KEYS = ("a1_guardian_name", "a2_name", "a3_peer1_name", "a3_peer1_friend", "a3_peer2_name", "a3_peer2_friend",
             "a2_about_9")                                    # Middle A2 "Name"


class ReadOnly(Exception):
    pass


def read_only_client(teacher_id: str) -> Portal:
    """The teacher's saved session, unable to send anything but GET."""
    with SessionLocal() as db:
        t = db.get(Teacher, teacher_id)
        if not t:
            raise SystemExit(f"no teacher with id {teacher_id}")
    client = hpc_sessions.portal_for("teacher", teacher_id)        # no credentials passed: never logs in
    original = client._request

    def guarded(method, path, **kwargs):
        if method.upper() != "GET":
            raise ReadOnly(f"blocked a {method} request: this tool is read only")
        return original(method, path, **kwargs)
    client._request = guarded
    client.save_part = lambda *a, **k: (_ for _ in ()).throw(ReadOnly("blocked a save: this tool is read only"))
    return client


def masked(key: str, value) -> str:
    text = str(value if value is not None else "").strip()
    if key in NAME_KEYS and text:
        return f"(name, {len(text)} letters)"
    return text or "-"


def fetch(client: Portal, stage: str, student_id: str):
    lookups = Lookups(client, stage_code(stage))
    data = sync.fetch_student(client, stage, student_id)
    return lookups, data


def show(stage: str, data, lookups) -> None:
    st = get_stage(stage)
    rec = data.record
    stu = rec.get("stu_info") or {}
    print(f"\nStudent {data.student_id} · stage {stage} · grade id {stu.get('grade_id')} · section id {stu.get('section_id')}")
    print(f"PARAKH status: current part = '{rec.get('current_part') or '-'}', hpc_status = '{rec.get('hpc_status') or '-'}'"
          f" · student name: {masked('a2_name', stu.get('student_name'))}")
    row = sync.to_row(stage, data, lookups)
    for part in st.PARTS:
        fields = part.fields(lookups)
        filled = [(f, row.get(f.key)) for f in fields if str(row.get(f.key) or "").strip()]
        print(f"\n== {part.title}: {len(filled)} of {len(fields)} fields filled")
        for f, v in filled:
            print(f"   {f.label}: {masked(f.key, v)}")
        if part.code == "B":
            fd = part.load(data.raw_parts.get(part.col))
            now = activity_grid.current(st.DOMAINS, fd)
            names = dict(zip(st.DOMAINS, st.SUBJECTS))
            print(f"   Activities on PARAKH: {len(now.existing)}" + (" (subjects overlap: locked in the grid)" if now.locked else ""))
            for i, e in enumerate(now.existing, start=1):
                levels = [fd[i - 1]["dt"].get(k, ["", "", "", ""])[3] or "-" for k in ("awr", "sen", "cre")] \
                    if i - 1 < len(fd) else ["?"] * 3
                print(f"   {i}. bank id {e['key'] or 'none (typed by the teacher)'} · finished: {'yes' if e['complete'] else 'no'}"
                      f" · levels A/S/C: {'/'.join(levels)} · subjects: {', '.join(names[s] for s in e['subjects']) or '-'}")


def preview(args) -> int:
    client = read_only_client(args.teacher)
    lookups, data = fetch(client, args.stage, args.student)
    path = snapshots.take(f"teacher_{args.teacher}", args.stage, data, "phase 3b stage 1 (read only)")
    print(f"Snapshot saved: {path.name} (in {path.parent})")
    show(args.stage, data, lookups)
    print("\nNothing was saved to PARAKH (this tool can only read).")
    return 0


def restore_preview(args) -> int:
    owner = f"teacher_{args.teacher}"
    entries = snapshots.list_for(owner, args.stage, args.student)
    if not entries:
        raise SystemExit("no snapshot for this student yet")
    chosen = args.snapshot or entries[0]["file"]
    old = snapshots.load(owner, args.stage, args.student, chosen)
    client = read_only_client(args.teacher)
    lookups, now = fetch(client, args.stage, args.student)
    before, after = sync.to_row(args.stage, old, lookups), sync.to_row(args.stage, now, lookups)
    st = get_stage(args.stage)
    labels = {f.key: (p.title, f.label) for p in st.PARTS for f in p.fields(lookups)}
    changed = [k for k in labels if str(before.get(k) or "") != str(after.get(k) or "")]
    raw_changed = [p.title for p in st.PARTS if old.raw_parts.get(p.col) != now.raw_parts.get(p.col)]
    print(f"Restore preview for student {args.student} from snapshot {chosen}:")
    if not changed and not raw_changed:
        print("   PARAKH holds exactly what the snapshot holds. A restore would change nothing.")
    for k in changed:
        part, label = labels[k]
        print(f"   {part} · {label}: now '{masked(k, after.get(k))}' -> restore '{masked(k, before.get(k))}'")
    extra = [t for t in raw_changed if not any(labels[k][0] == t for k in changed)]
    if extra:
        print(f"   Also different in stored data the workbook does not show: {', '.join(extra)}")
    print("Nothing was saved (preview only).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["preview", "restore-preview"])
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--stage", required=True, choices=["Foundational", "Preparatory", "Middle"])
    ap.add_argument("--student", required=True)
    ap.add_argument("--snapshot")
    args = ap.parse_args()
    try:
        return preview(args) if args.command == "preview" else restore_preview(args)
    except (PortalError, ReadOnly) as exc:
        print(f"Stopped: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
