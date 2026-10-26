"""
Phase 3b, stage 2: the ONLY tool here that writes to PARAKH. Every command needs --confirm, takes a
fresh snapshot first, and checks PARAKH again afterwards. Output carries IDs only.

    python scripts/phase3b_write.py noop-a1 --teacher <id> --stage Preparatory --student <id> --confirm SAVE
        One request: part A1 with exactly the values PARAKH holds and current part unchanged.
        Refuses unless the A1 data it would send is byte-for-byte what PARAKH holds.
    python scripts/phase3b_write.py part-b-plan --teacher <id> --stage <s> --student <id>
        Live test steps 2-4: what Part B the app would send now (dashboard + Activity Library); sends nothing.
    python scripts/phase3b_write.py part-b --teacher <id> --stage <s> --student <id> --confirm SAVE
        One request: part B as planned, current part unchanged. Then checks that PARAKH stored exactly what
        was sent and that no other part changed.
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
from backend.hpc.stages import activity_grid, get_stage  # noqa: E402
from backend.hpc.stages.common import Lookups  # noqa: E402
from backend.services import hpc_sessions, snapshots  # noqa: E402
from phase3b import diff  # noqa: E402


def client_for(teacher_id: str):
    return hpc_sessions.portal_for("teacher", teacher_id)       # the session the teacher opened; never logs in


def _parse(v):
    return json.loads(v) if isinstance(v, str) and v.strip() else v


def compare(label: str, a: sync.StudentData, b: sync.StudentData, stage: str, skip=()) -> int:
    """Prints how b differs from a (current part and every part's data, except `skip`); returns the count."""
    n = 0
    if (a.record.get("current_part") or "") != (b.record.get("current_part") or ""):
        print(f"   current part: '{a.record.get('current_part')}' -> '{b.record.get('current_part')}'")
        n += 1
    for part in get_stage(stage).PARTS:
        if part.col in skip:
            continue
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


# ---------------------------------------------------------------------------
# Live test steps 2-4: Part B as the app would save it now
# ---------------------------------------------------------------------------

def resolver_for(teacher_id: str, stage: str, lookups):
    """The same activity resolver a real save uses (the teacher's Activity Library, with their own versions)."""
    from backend.services.activity_library import resolver_for_teacher
    return resolver_for_teacher(teacher_id, stage, fallback=activity_grid.resolver_from_lookups(lookups))


def dashboard_for(teacher_id: str, session: str, stage: str, student_id: str, lookups):
    """Everything about Part B the dashboard holds for the student (grid and Part B answers)."""
    from backend.services.class_template import dashboard_values
    return dashboard_values(teacher_id, session, stage, student_id, lookups)


def describe(label: str, fd, names) -> None:
    """One line per activity on the card: kind (bank / manual), library key, subjects, levels. IDs only."""
    print(label)
    for act in _parse(fd) or []:
        dt = act.get("dt") or {}
        if not (dt.get("act_bank_id") or dt.get("domain")):
            continue
        bank = dt.get("act_bank_id")
        if bank:
            kind = f"from the bank #{bank} ({'global' if dt.get('is_global', True) is not False else 'my activities'})"
            key = activity_grid.key_for(bank, dt.get("is_global"))
        else:
            kind = "MANUAL (no bank number)"
            key = names.key_of(act) or "not from this app"
        levels = "/".join(str((dt.get(k) or ["", "", "", ""])[3]) for k in ("awr", "sen", "cre"))
        print(f"   {act.get('id') or '(new)'}: {kind}, is_modified={act.get('is_modified')!r}, library {key}, "
              f"subjects {','.join(dt.get('domain') or [])}, levels {levels}")


def plan_part_b(args, client):
    """(before, Part B request, resolver, Part B problems) - built by the same code a real save runs."""
    lookups = Lookups(client, stage_code(args.stage))
    resolve = resolver_for(args.teacher, args.stage, lookups)
    before = sync.fetch_student(client, args.stage, args.student)
    row = {**sync.to_row(args.stage, before, lookups),
           **dashboard_for(args.teacher, client.ay, args.stage, args.student, lookups)}
    payloads, errors = sync.build_payloads(args.stage, before, row, lookups, resolve)
    title = next(p.title for p in get_stage(args.stage).PARTS if p.code == "B")
    problems = [e for e in errors if e.startswith(f"{title}:")]
    request = dict(next(p for p in payloads if p["hpc_col"] == "part_b"))
    request["current_part"] = before.record.get("current_part") or request["current_part"]
    request.pop("hpc_status", None)                     # one part only: the card's status is not touched
    names = activity_grid.typed_keys(resolve)
    describe("On PARAKH now:", before.raw_parts.get("part_b"), names)
    describe("The app would send:", request["formdata"], names)
    print(f"   act_bank_map: {request.get('act_bank_map')}")
    return before, request, resolve, problems


def part_b_plan(args) -> int:
    client = client_for(args.teacher)
    before, request, _, problems = plan_part_b(args, client)
    for p in problems:
        print(f"   PROBLEM: {p}")
    same = not diff(_parse(before.raw_parts.get("part_b")), _parse(request["formdata"]))
    print("Part B would not change: nothing to send." if same else
          f"Would send ONE request: part_b, current part '{request['current_part']}'.")
    print("Nothing was sent (plan only).")
    return 1 if problems else 0


def part_b_save(args) -> int:
    if args.confirm != "SAVE":
        raise SystemExit("not sent: add --confirm SAVE")
    client = client_for(args.teacher)
    writes = guard_one_write(client)
    before, request, resolve, problems = plan_part_b(args, client)
    if problems:
        raise SystemExit("not sent: Part B has problems - " + "; ".join(problems))
    if not diff(_parse(before.raw_parts.get("part_b")), _parse(request["formdata"])):
        raise SystemExit("not sent: Part B would not change")
    status_before = roster_status(client, args.stage, args.student)
    snap = snapshots.take(f"teacher_{args.teacher}", args.stage, before, "live test Part B - before")
    print(f"Before: current part '{before.record.get('current_part')}', class list status '{status_before}'. Snapshot {snap.name}.")
    print(f"Sending ONE request: part_b, current part '{request['current_part']}'.")

    response = client.save_part(args.stage, args.student, request)
    data = response.get("data")
    print(f"HTTP status {getattr(client, 'last_status', '?')}; response: success={response.get('success')!r}, "
          f"message={str(response.get('message') or '')[:60]!r}, "
          f"data={'keys ' + ', '.join(sorted(data)) if isinstance(data, dict) else type(data).__name__}")
    print(f"Write requests sent: {len(writes)} ({', '.join(m for m, _ in writes)})")
    remember = getattr(resolve, "remember", None)
    if remember:
        remember(_parse(request["formdata"]))           # which manual activities on this card are the app's own

    after = sync.fetch_student(client, args.stage, args.student)
    status_after = roster_status(client, args.stage, args.student)
    snapshots.take(f"teacher_{args.teacher}", args.stage, after, "live test Part B - after")
    describe("On PARAKH after the save:", after.raw_parts.get("part_b"), activity_grid.typed_keys(resolve))
    others = compare("Other parts and current part, compared with before", before, after, args.stage, skip=("part_b",))
    stored = diff(_parse(request["formdata"]), _parse(after.raw_parts.get("part_b")))
    for path, _, _ in stored:
        print(f"   part_b {path}: PARAKH stored something else than was sent")
    print(f"Part B as stored, compared with what was sent: {'no differences' if not stored else f'{len(stored)} difference(s)'}")
    print(f"After: current part '{after.record.get('current_part')}', class list status '{status_after}'.")
    ok = others == 0 and not stored and status_after == status_before
    if not ok:
        print("\nSTOP: something is not as expected. The restore plan is below; NOTHING more is sent without your approval.")
        restore_plan(SimpleNamespace(teacher=args.teacher, stage=args.stage, student=args.student,
                                     snapshot=snap.name, confirm=""), send=False)
        return 2
    print("All checks passed: Part B stored as sent, nothing else changed, status as before.")
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
    ap.add_argument("command", choices=["noop-a1", "part-b-plan", "part-b", "restore-plan", "restore"])
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--stage", required=True, choices=["Foundational", "Preparatory", "Middle"])
    ap.add_argument("--student", required=True)
    ap.add_argument("--snapshot")
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()
    try:
        if args.command == "noop-a1":
            return noop_a1(args)
        if args.command == "part-b-plan":
            return part_b_plan(args)
        if args.command == "part-b":
            return part_b_save(args)
        return restore_plan(args, send=args.command == "restore")
    except PortalError as exc:
        print(f"Stopped: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
