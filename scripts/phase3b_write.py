"""
Phase 3b, stage 2: the ONLY tool here that writes to PARAKH. Every command needs --confirm, takes a
fresh snapshot first, and checks PARAKH again afterwards. Output carries IDs only.

    python scripts/phase3b_write.py noop-a1 --teacher <id> --stage Preparatory --student <id> --confirm SAVE
        One request: part A1 with exactly the values PARAKH holds and current part unchanged.
        Refuses unless the A1 data it would send is byte-for-byte what PARAKH holds.
    python scripts/phase3b_write.py restore-plan --teacher <id> --stage <s> --student <id> [--snapshot <file>]
        Shows the restore requests (sends nothing).
    python scripts/phase3b_write.py restore --teacher <id> --stage <s> --student <id> --snapshot <file> --confirm RESTORE
        Puts every part back exactly as in the snapshot, in order, ending at the snapshot's current part.
"""
import argparse
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.hpc import sync  # noqa: E402
from backend.hpc.portal import PortalError, stage_code  # noqa: E402
from backend.hpc.stages import get_stage  # noqa: E402
from backend.hpc.stages.common import Lookups  # noqa: E402
from backend.services import hpc_sessions, snapshots  # noqa: E402
from phase3b import diff  # noqa: E402


def client_for(teacher_id: str):
    return hpc_sessions.portal_for("teacher", teacher_id)       # the session the teacher opened; never logs in


def _parse(v):
    return json.loads(v) if isinstance(v, str) and v.strip() else v


def compare(label: str, a: sync.StudentData, b: sync.StudentData, stage: str) -> int:
    """Prints how b differs from a (current part and every part's data); returns the number of differences."""
    n = 0
    if (a.record.get("current_part") or "") != (b.record.get("current_part") or ""):
        print(f"   current part: '{a.record.get('current_part')}' -> '{b.record.get('current_part')}'")
        n += 1
    for part in get_stage(stage).PARTS:
        d = diff(_parse(a.raw_parts.get(part.col)), _parse(b.raw_parts.get(part.col)))
        for path, _, _ in d:
            print(f"   {part.col} {path}: changed")                 # where only: values may be personal
        n += len(d)
    print(f"{label}: {'no differences' if n == 0 else f'{n} difference(s)'}")
    return n


def restore_requests(stage: str, old: sync.StudentData, lookups) -> list:
    """The requests that put a snapshot back: each part's stored data exactly as it was, in the portal's
    order, with the extra keys a save needs; the last request ends at the snapshot's current part."""
    built, _ = sync.build_payloads(stage, old, sync.to_row(stage, old, lookups), lookups)
    parts = get_stage(stage).PARTS
    end = old.record.get("current_part") or "mc"
    out = []
    for i, (part, payload) in enumerate(zip(parts, built)):
        req = {k: v for k, v in payload.items() if k not in ("formdata", "hpc_status")}
        raw = old.raw_parts.get(part.col)
        req["formdata"] = copy.deepcopy(raw) if not part.as_json_string or isinstance(raw, str) else json.dumps(raw)
        last = i == len(parts) - 1
        req["current_part"] = end if last else parts[i + 1].code
        if last and end == "mc":
            req["hpc_status"] = "COMPLETED"
        out.append(req)
    return out


def guard_one_write(client):
    """Counts every non-GET request and stops any after the first, before it leaves; no session renewal."""
    original = client._request
    sent = []

    def guarded(method, path, **kwargs):
        if method.upper() != "GET":
            if sent:
                raise PortalError(f"blocked a second write ({method}): stage 2a sends exactly one request")
            sent.append((method.upper(), path))
        return original(method, path, **kwargs)
    client._request = guarded
    client.refresh = lambda rejected_token: False           # renewing is a POST too: not during stage 2a
    return sent


def roster_status(client, stage: str, student_id: str) -> str:
    """The card's status as the class list shows it (GET only)."""
    for r in client.roster(stage):
        if str(r.get("id")) == str(student_id):
            return str(r.get("hpc_status") or "")
    return "(not on this teacher's list)"


def noop_a1(args) -> int:
    if args.confirm != "SAVE":
        raise SystemExit("not sent: add --confirm SAVE")
    client = client_for(args.teacher)
    writes = guard_one_write(client)
    lookups = Lookups(client, stage_code(args.stage))
    before = sync.fetch_student(client, args.stage, args.student)
    status_before = roster_status(client, args.stage, args.student)
    snap = snapshots.take(f"teacher_{args.teacher}", args.stage, before, "phase 3b stage 2a (no-op A1) - before")
    payloads, errors = sync.build_payloads(args.stage, before, sync.to_row(args.stage, before, lookups), lookups)
    a1 = dict(payloads[0])
    if a1["hpc_col"] != "part_a1" or a1["formdata"] != before.raw_parts.get("part_a1"):
        raise SystemExit("not sent: the A1 data is not byte-for-byte what PARAKH holds")
    stu = before.record.get("stu_info") or {}
    held = {"cond_class": before.record.get("cond_class"), "med_inst": stu.get("med_inst"),
            "location_id": stu.get("location_id")}
    for key, value in held.items():
        same = str(a1.get(key)) == str(value)
        print(f"   {key}: sending {a1.get(key)!r}, PARAKH holds {value!r} -> {'same' if same else 'DIFFERENT'}")
        if not same:
            raise SystemExit(f"not sent: {key} differs from what PARAKH holds")
    a1["current_part"] = before.record.get("current_part") or a1["current_part"]
    print(f"Before: current part '{before.record.get('current_part')}', class list status '{status_before}'. Snapshot {snap.name}.")
    print(f"Sending ONE request: part_a1, identical data, current part '{a1['current_part']}'.")

    response = client.save_part(args.stage, args.student, a1)
    data = response.get("data")
    print(f"HTTP status {getattr(client, 'last_status', '?')}; response: success={response.get('success')!r}, "
          f"message={str(response.get('message') or '')[:60]!r}, "
          f"data={'keys ' + ', '.join(sorted(data)) if isinstance(data, dict) else type(data).__name__}")
    print(f"Write requests sent: {len(writes)} ({', '.join(m for m, _ in writes)})")

    after = sync.fetch_student(client, args.stage, args.student)
    status_after = roster_status(client, args.stage, args.student)
    snapshots.take(f"teacher_{args.teacher}", args.stage, after, "phase 3b stage 2a (no-op A1) - after")
    changed = compare("After the no-op save, compared with the snapshot", before, after, args.stage)
    print(f"After: current part '{after.record.get('current_part')}', class list status '{status_after}'.")
    ok = changed == 0 and after.record.get("current_part") == "mc" and status_after == status_before == "COMPLETED"
    if not ok:
        print("\nSTOP: something is not as before. The restore plan is below; NOTHING more is sent without your approval.")
        restore_plan(SimpleNamespace(teacher=args.teacher, stage=args.stage, student=args.student,
                                     snapshot=snap.name, confirm=""), send=False)
        return 2
    print("All checks passed: same data, current part 'mc', status COMPLETED.")
    return 0


def restore_plan(args, send: bool = False) -> int:
    owner = f"teacher_{args.teacher}"
    entries = snapshots.list_for(owner, args.stage, args.student)
    chosen = args.snapshot or (entries[-1]["file"] if entries else None)     # default: the OLDEST copy
    if not chosen:
        raise SystemExit("no snapshot for this student")
    old = snapshots.load(owner, args.stage, args.student, chosen)
    client = client_for(args.teacher)
    lookups = Lookups(client, stage_code(args.stage))
    requests = restore_requests(args.stage, old, lookups)
    print(f"Restore from snapshot {chosen}: {len(requests)} request(s), in this order:")
    for r in requests:
        print(f"   {r['hpc_col']}: stored data as in the snapshot, current part -> '{r['current_part']}'"
              + (", status COMPLETED" if r.get("hpc_status") else ""))
    if not send:
        print("Nothing was sent (plan only).")
        return 0
    if args.confirm != "RESTORE":
        raise SystemExit("not sent: add --confirm RESTORE")
    now = sync.fetch_student(client, args.stage, args.student)
    snapshots.take(owner, args.stage, now, f"before restore from {chosen}")
    for r in requests:
        client.save_part(args.stage, args.student, r)
    after = sync.fetch_student(client, args.stage, args.student)
    return 0 if compare("After the restore, compared with the snapshot", old, after, args.stage) == 0 else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["noop-a1", "restore-plan", "restore"])
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--stage", required=True, choices=["Foundational", "Preparatory", "Middle"])
    ap.add_argument("--student", required=True)
    ap.add_argument("--snapshot")
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()
    try:
        if args.command == "noop-a1":
            return noop_a1(args)
        return restore_plan(args, send=args.command == "restore")
    except PortalError as exc:
        print(f"Stopped: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
