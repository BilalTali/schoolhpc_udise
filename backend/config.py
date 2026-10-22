"""
Application Configuration
"""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
AUTOMATION_ROOT = PROJECT_ROOT / "hpc_python_automation"

# MySQL Database connection (XAMPP default: root without password on 127.0.0.1:3306)
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_DB = os.getenv("MYSQL_DB", "hpc_automation")

DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"

# Fallback SQLite DB for offline testing if MySQL is ever down
SQLITE_URL = f"sqlite:///{AUTOMATION_ROOT / 'data' / 'hpc_automation.db'}"

# JWT Security
JWT_SECRET = os.getenv("JWT_SECRET", "hpc_enterprise_super_secret_key_parakh_2026_@_987654321")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Storage directories
SESSIONS_DIR = AUTOMATION_ROOT / "data" / "teacher_sessions"
EVIDENCE_DIR = AUTOMATION_ROOT / "audit_evidence"
DATA_DIR = AUTOMATION_ROOT / "data"

for d in (SESSIONS_DIR, EVIDENCE_DIR, DATA_DIR):
    d.mkdir(parents=True, exist_ok=True)
