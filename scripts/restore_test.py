"""
Proves the newest backup can be restored: decrypts it in memory, loads it into a scratch database
(hpc_restore_test), dumps that scratch copy again and compares it table by table with the backup.
Also checks that the data-folder archive decrypts and opens. The real database is never touched
and no decrypted file is written to disk. Prints PASS/FAIL; non-zero exit code on failure.

    python scripts/restore_test.py [path/to/db_backup.sql.enc]
"""
import io
import re
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backup_db import BACKUP_DIR, DB, MYSQL_BIN, backup_key  # noqa: E402

SCRATCH = "hpc_restore_test"
CRLF, LF = chr(13) + chr(10), chr(10)        # mysqldump on Windows may write either


def mysql(*args: str, stdin: bytes = None) -> str:
    return subprocess.run([str(MYSQL_BIN / "mysql.exe"), "-u", "root", *args], input=stdin, check=True,
                          capture_output=True).stdout.decode("utf-8")


def tables(dump_text: str) -> dict:
    """Table -> (CREATE statement, INSERT statements) with AUTO_INCREMENT counters removed."""
    text = dump_text.replace(CRLF, LF)
    out = {}
    for m in re.finditer(r"CREATE TABLE `(\w+)` \((.*?)\) ENGINE[^;]*;", text, re.S):
        name = m.group(1)
        inserts = re.findall(rf"INSERT INTO `{name}` VALUES .*?;{LF}", text, re.S)
        out[name] = (re.sub(r"AUTO_INCREMENT=\d+ ", "", m.group(0)), "".join(inserts))
    return out


def main() -> int:
    box = backup_key()
    backup = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(BACKUP_DIR.glob(f"db_{DB}_*.sql.enc"))[-1]
    if SCRATCH == DB:
        raise SystemExit("refusing to restore into the real database")
    plain = box.decrypt(backup.read_bytes())
    mysql("-e", f"DROP DATABASE IF EXISTS {SCRATCH}; "
                f"CREATE DATABASE {SCRATCH} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    mysql(SCRATCH, stdin=plain)
    again = subprocess.run([str(MYSQL_BIN / "mysqldump.exe"), "-u", "root", "--routines", "--triggers", SCRATCH],
                           check=True, capture_output=True).stdout.decode("utf-8")
    original, restored = tables(plain.decode("utf-8")), tables(again)
    problems = [t for t in original if original[t] != restored.get(t)] + [t for t in restored if t not in original]
    for t in sorted(original):
        rows = mysql("-N", "-e", f"SELECT COUNT(*) FROM {SCRATCH}.`{t}`").strip()
        print(f"  {t:28} rows {rows:>6}  {'same' if t not in problems else 'DIFFERENT'}")

    data = backup.with_name(backup.name.replace(f"db_{DB}_", "data_").replace(".sql.enc", ".tar.gz.enc"))
    files = 0
    if data.exists():
        with tarfile.open(fileobj=io.BytesIO(box.decrypt(data.read_bytes())), mode="r:gz") as tar:
            files = sum(1 for m in tar.getmembers() if m.isfile())
    print(f"  data archive {data.name}: {files} files" if data.exists() else "  data archive: missing")

    verdict = "PASS" if original and not problems and files > 0 else "FAIL"
    print(f"restore test {verdict}: {backup.name} -> {SCRATCH} ({len(original)} tables)")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
