"""
Repository: persists and retrieves student upload statuses and execution logs in SQLite.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from database.models import StudentUploadLog, UploadState

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "hpc_automation.db"


class UploadRepository:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS upload_logs (
                    admission_number TEXT PRIMARY KEY,
                    student_name TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER DEFAULT 0,
                    last_attempt_at TEXT,
                    completed_at TEXT,
                    error_message TEXT,
                    screenshot_evidence TEXT
                )
            """)
            conn.commit()

    def get_log(self, admission_number: str) -> Optional[StudentUploadLog]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT admission_number, student_name, stage, status, attempt_count, "
                "last_attempt_at, completed_at, error_message, screenshot_evidence "
                "FROM upload_logs WHERE admission_number = ?",
                (admission_number,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return StudentUploadLog(
                admission_number=row[0],
                student_name=row[1],
                stage=row[2],
                status=UploadState(row[3]),
                attempt_count=row[4],
                last_attempt_at=datetime.fromisoformat(row[5]) if row[5] else None,
                completed_at=datetime.fromisoformat(row[6]) if row[6] else None,
                error_message=row[7],
                screenshot_evidence=row[8],
            )

    def record_attempt(self, admission_number: str, student_name: str, stage: str = "Preparatory"):
        with self._get_connection() as conn:
            now = datetime.now().isoformat()
            conn.execute("""
                INSERT INTO upload_logs (admission_number, student_name, stage, status, attempt_count, last_attempt_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(admission_number) DO UPDATE SET
                    attempt_count = attempt_count + 1,
                    stage = excluded.stage,
                    status = 'IN_PROGRESS',
                    error_message = NULL,
                    last_attempt_at = ?
            """, (admission_number, student_name, stage, UploadState.IN_PROGRESS.value, now, now))
            conn.commit()

    def record_success(self, admission_number: str, screenshot: Optional[str] = None):
        with self._get_connection() as conn:
            now = datetime.now().isoformat()
            conn.execute("""
                UPDATE upload_logs
                SET status = ?, completed_at = ?, error_message = NULL, screenshot_evidence = ?
                WHERE admission_number = ?
            """, (UploadState.SUCCESS.value, now, screenshot, admission_number))
            conn.commit()

    def record_failure(self, admission_number: str, error_message: str):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE upload_logs
                SET status = ?, error_message = ?
                WHERE admission_number = ?
            """, (UploadState.FAILED.value, error_message, admission_number))
            conn.commit()

    def get_all_logs(self) -> List[StudentUploadLog]:
        logs = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT admission_number, student_name, stage, status, attempt_count, last_attempt_at, completed_at, error_message, screenshot_evidence FROM upload_logs ORDER BY last_attempt_at DESC")
            for row in cursor.fetchall():
                logs.append(StudentUploadLog(
                    admission_number=row[0],
                    student_name=row[1],
                    stage=row[2],
                    status=UploadState(row[3]),
                    attempt_count=row[4],
                    last_attempt_at=datetime.fromisoformat(row[5]) if row[5] else None,
                    completed_at=datetime.fromisoformat(row[6]) if row[6] else None,
                    error_message=row[7],
                    screenshot_evidence=row[8],
                ))
        return logs
