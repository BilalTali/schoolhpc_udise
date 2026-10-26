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
             "a2_about_9",                                    # Middle A2 "Name"
             "a1_udid",                                       # disability ID: personal identifier
             "a3_resources_other", "a4_resources_other")     # free text that has held names


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
    client.refresh = lambda rejected_token: False      # renewing the session is a POST: not in a read-only run
    return client


def masked(key: str, value) -> str:
    text = str(value if value is not None else "").strip()
    if key in NAME_KEYS and text:
        return f"(hidden, {len(text)} characters)"
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


# Places in each part's formdata that hold personal identifiers: shown as (hidden, N characters).
PERSONAL_PATHS = {
    "part_a1": {"basic[0]", "basic[1]", "basic[2]", "gen[1]", "gen[4]", "gen[21]", "gen[22]", "gen[24]", "gen[25]"},
    "part_a2": {"gen[0]"},
    "part_a3": {"pr1[0]", "pr1[1]", "pr2[0]", "pr2[1]", "mtr_oth"},
}


def _parse(value):
    import json
    if isinstance(value, str):
        try:
            return json.loads(value) if value.strip() else None
        except ValueError:
            return value
    return value


def diff(old, new, path=""):
    """Every place where the two structures differ: (path, old value, new value)."""
    out = []
    if isinstance(old, dict) and isinstance(new, dict):
        for k in list(old) + [k for k in new if k not in old]:
            p = f"{path}.{k}" if path else str(k)
            if k not in new:
                out.append((p, old[k], "<missing>"))
            elif k not in old:
                out.append((p, "<missing>", new[k]))
            else:
                out += diff(old[k], new[k], p)
    elif isinstance(old, list) and isinstance(new, list):
        for i in range(max(len(old), len(new))):
            p = f"{path}[{i}]"
            if i >= len(new):
                out.append((p, old[i], "<missing>"))
            elif i >= len(old):
                out.append((p, "<missing>", new[i]))
            else:
                out += diff(old[i], new[i], p)
    elif old != new:
        out.append((path, old, new))
    return out


def _show(col, path, value):
    import json
    if any(path == p or path.startswith(p + ".") or path.startswith(p + "[") for p in PERSONAL_PATHS.get(col, ())):
        text = value if isinstance(value, str) else json.dumps(value)
        return f"(hidden, {len(text)} characters)" if text not in ("", '""') else "''"
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 70 else text[:67] + "..."


def dry_run(args) -> int:
    """Builds exactly what a save would send (no edits) and diffs it with what PARAKH holds. Sends nothing."""
    client = read_only_client(args.teacher)
    lookups, data = fetch(client, args.stage, args.student)
    row = sync.to_row(args.stage, data, lookups)                 # the card as it is: nothing edited
    payloads, errors = sync.build_payloads(args.stage, data, row, lookups)
    st = get_stage(args.stage)
    print(f"Round-trip dry run, student {args.student}: PARAKH current part = '{data.current_part}'. Nothing is sent.")
    if errors:
        print("Checks a real save would fail on:")
        for e in errors:
            print(f"   - {e}")
    for part, payload in zip(st.PARTS, payloads):
        stored, sent = _parse(data.raw_parts.get(part.col)), _parse(payload["formdata"])
        changes = diff(stored, sent)
        extra = {k: v for k, v in payload.items() if k not in ("formdata",)}
        text_same = payload["formdata"] == data.raw_parts.get(part.col) if part.as_json_string else None
        print(f"\n== {part.title} ({part.col}): {len(changes)} difference(s) in the data")
        print(f"   request keys besides the data: {json_short(extra)}")
        if text_same is not None:
            print(f"   stored text byte-for-byte identical to what would be sent: {'yes' if text_same else 'no'}")
        for p, a, b in changes:
            print(f"   {p}: PARAKH {_show(part.col, p, a)} -> save {_show(part.col, p, b)}")
    a1 = dict(payloads[0])
    a1["current_part"] = data.current_part or a1["current_part"]
    print(f"\nStage 2a would send ONE request: part_a1 with current_part = '{a1['current_part']}' "
          f"(a normal save would send '{payloads[0]['current_part']}'), and nothing for the other parts.")
    return 0


def json_short(value) -> str:
    import json
    return json.dumps(value, ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["preview", "restore-preview", "dry-run"])
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--stage", required=True, choices=["Foundational", "Preparatory", "Middle"])
    ap.add_argument("--student", required=True)
    ap.add_argument("--snapshot")
    args = ap.parse_args()
    try:
        return {"preview": preview, "restore-preview": restore_preview, "dry-run": dry_run}[args.command](args)
    except (PortalError, ReadOnly) as exc:
        print(f"Stopped: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
