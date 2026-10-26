"""Retention: snapshots older than 400 days go (each student's newest 2 stay); backups keep 14 + 8 weekly."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.services import snapshots

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import backup_db  # noqa: E402


def _snapshot(folder: Path, when: datetime) -> Path:
    p = folder / f"{when:%Y%m%dT%H%M%S%fZ}.json"
    p.write_text("{}", encoding="utf-8")
    return p


def test_old_snapshots_go_but_each_student_keeps_two(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path)
    now = datetime.now(timezone.utc)
    a = tmp_path / "teacher_x" / "preparatory" / "1001"
    b = tmp_path / "teacher_x" / "middle" / "2001"
    a.mkdir(parents=True), b.mkdir(parents=True)
    old_a = [_snapshot(a, now - timedelta(days=d)) for d in (900, 800, 700, 600)]   # all older than 400 days
    recent_a = _snapshot(a, now - timedelta(days=10))
    only_b = [_snapshot(b, now - timedelta(days=d)) for d in (999, 998)]             # only two, both old

    removed = snapshots.prune(max_age_days=400, keep_last=2)
    assert removed == 3                                          # 900, 800, 700 days; 600 is among the newest 2
    assert sorted(p.name for p in a.iterdir()) == sorted([old_a[3].name, recent_a.name])
    assert all(p.exists() for p in only_b)                       # a student's last restore points stay


def test_backups_keep_the_newest_14_and_one_per_week_for_8_weeks(tmp_path):
    now = datetime.now()
    files = [tmp_path / f"db_hpc_automation_{now - timedelta(days=d):%Y%m%d_%H%M%S}.sql.enc" for d in range(70)]
    kept = backup_db.keep(files)
    newest_14 = set(sorted(files)[-14:])
    assert newest_14 <= kept
    older = kept - newest_14
    weeks = {datetime.strptime(f.name[18:33], "%Y%m%d_%H%M%S").isocalendar()[:2] for f in older}
    assert len(older) == len(weeks) and 5 <= len(older) <= 7     # one per week, only within the last 8 weeks
    assert all(now - datetime.strptime(f.name[18:33], "%Y%m%d_%H%M%S") <= timedelta(weeks=8) for f in kept)
