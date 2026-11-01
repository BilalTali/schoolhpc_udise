"""
Prints the data completeness report (backend/hpc/completeness.py) for every card the app has a stored copy of
(data/cards/<owner>/<session>/<stage>/<student>.json) - offline, nothing is sent anywhere.

    python scripts/completeness_report.py                       # every stored card
    python scripts/completeness_report.py --stage middle        # one stage
    python scripts/completeness_report.py --student 110087      # one student (PARAKH student id)
    python scripts/completeness_report.py --summary             # counts per student only

The stored copy is what PARAKH held when the app last read the card; drafts not yet saved are not included.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.hpc import completeness  # noqa: E402
from backend.services import card_store  # noqa: E402

STAGES = {"foundational": "FOUNDATIONAL", "preparatory": "PREPARATORY", "middle": "MIDDLE"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=sorted(STAGES))
    ap.add_argument("--student")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()
    paths = sorted(card_store.CARDS_DIR.glob("*/*/*/*.json"))
    shown = 0
    for path in paths:
        stage = path.parent.name
        if stage not in STAGES or (args.stage and stage != args.stage) or (args.student and path.stem != args.student):
            continue
        stored = card_store._load(path)
        parts = stored.get("parts") or {}
        record = parts.get(card_store.RECORD) if isinstance(parts.get(card_store.RECORD), dict) else {}
        rep = completeness.report(STAGES[stage], parts, record)
        shown += 1
        if args.summary:
            counts = {k: sum(len(v[k]) for v in rep["sections"].values()) for k in completeness.KINDS}
            print(f"{path.stem:>8}  {stage:<12} {rep['student'][:28]:<28} " +
                  "  ".join(f"{k} {n}" for k, n in counts.items()))
        else:
            print(f"--- {path.stem} ---")
            print(completeness.as_text(rep))
            print()
    if not shown:
        print("No stored cards matched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
