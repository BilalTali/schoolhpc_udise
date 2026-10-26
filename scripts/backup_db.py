"""
Encrypted backup of the app: the MySQL database and the data folder (drafts, class lists,
snapshots, PARAKH sessions, the app's own keys). Both are encrypted in memory with the backup
key (Fernet: AES-128-CBC + HMAC-SHA256) before anything is written, so no plain copy ever
reaches the disk. Also applies the retention rules.

    python scripts/backup_db.py            (run daily by Windows Task Scheduler, see README)

Settings come from .env (backend/config.py): HPC_DATA_DIR, HPC_BACKUP_DIR, HPC_BACKUP_KEY_FILE,
plus HPC_MYSQL_BIN (default C:/xampp/mysql/bin) and HPC_DB_NAME (default hpc_automation).

Retention
  backups    the newest 14, plus the newest one of each of the last 8 weeks
  snapshots  kept 400 days; older ones go, except each student's newest 2
"""
import io
import os
import re
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
from backend.config import BACKUP_DIR, BACKUP_KEY_FILE, DATA_DIR  # noqa: E402  (also loads .env)

from cryptography.fernet import Fernet  # noqa: E402

MYSQL_BIN = Path(os.getenv("HPC_MYSQL_BIN", "C:/xampp/mysql/bin"))
DB = os.getenv("HPC_DB_NAME", "hpc_automation")
KEEP_DAILY, KEEP_WEEKS = 14, 8


def backup_key() -> Fernet:
    """The backup key is created once and kept OUTSIDE the backup folder. Keep an offline copy:
    without it the backups cannot be opened."""
    if not BACKUP_KEY_FILE.exists():
        BACKUP_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        BACKUP_KEY_FILE.write_bytes(Fernet.generate_key())
        print(f"created a new backup key at {BACKUP_KEY_FILE} - copy it somewhere safe and offline")
    if BACKUP_KEY_FILE.parent.resolve() == BACKUP_DIR.resolve():
        raise SystemExit("the backup key must not be stored in the backup folder")
    return Fernet(BACKUP_KEY_FILE.read_bytes().strip())


def dump_database() -> bytes:
    raw = subprocess.run([str(MYSQL_BIN / "mysqldump.exe"), "-u", "root", "--single-transaction", "--routines",
                          "--triggers", DB], check=True, capture_output=True).stdout
    if b"Dump completed" not in raw[-200:]:
        raise RuntimeError("the database dump looks incomplete (no 'Dump completed' line)")
    return raw


def archive_data() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(DATA_DIR, arcname="data")
    return buf.getvalue()


def keep(files):
    """The newest KEEP_DAILY, plus the newest of each of the last KEEP_WEEKS ISO weeks."""
    files = sorted(files)
    kept = set(files[-KEEP_DAILY:])
    cutoff = datetime.now() - timedelta(weeks=KEEP_WEEKS)
    weekly = {}
    for f in files:
        found = re.search(r"(\d{8}_\d{6})", f.name)
        if not found:
            continue
        stamp = datetime.strptime(found.group(1), "%Y%m%d_%H%M%S")
        if stamp >= cutoff:
            weekly[stamp.isocalendar()[:2]] = f                       # sorted, so the newest of the week wins
    return kept | set(weekly.values())


def prune(pattern: str) -> int:
    files = list(BACKUP_DIR.glob(pattern))
    removed = 0
    for f in set(files) - keep(files):
        f.unlink()
        removed += 1
    return removed


def main() -> int:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    box = backup_key()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sql = BACKUP_DIR / f"db_{DB}_{stamp}.sql.enc"
    sql.write_bytes(box.encrypt(dump_database()))
    data = BACKUP_DIR / f"data_{stamp}.tar.gz.enc"
    data.write_bytes(box.encrypt(archive_data()))
    removed = prune(f"db_{DB}_*.sql.enc") + prune("data_*.tar.gz.enc")
    from backend.services import snapshots
    gone = snapshots.prune()
    print(f"{datetime.now():%Y-%m-%d %H:%M} backup ok: {sql.name} ({sql.stat().st_size:,} bytes), "
          f"{data.name} ({data.stat().st_size:,} bytes); removed {removed} old backup(s), {gone} old snapshot(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
