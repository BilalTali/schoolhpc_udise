"""
Application settings. Override any of them with environment variables (or a .env file
in the project root, see .env.example).
"""
import os
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not line.lstrip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(PROJECT_ROOT / ".env")

# Database: MySQL from XAMPP by default; set HPC_DATABASE_URL to use something else,
# e.g. sqlite:///data/hpc.db
DATABASE_URL = os.getenv("HPC_DATABASE_URL", "mysql+pymysql://root:@127.0.0.1:3306/hpc_automation?charset=utf8mb4")

# Local files: portal sessions, uploaded workbooks, generated workbooks. Never committed.
# Keep these OUTSIDE cloud-synced folders (OneDrive, Google Drive): they hold students' records,
# PARAKH session tokens and the keys that unlock stored passwords. Set them in .env.
DATA_DIR = Path(os.getenv("HPC_DATA_DIR", PROJECT_ROOT / "data"))
SESSIONS_DIR = DATA_DIR / "sessions"
BACKUP_DIR = Path(os.getenv("HPC_BACKUP_DIR", PROJECT_ROOT.parent / "hhpc_backups"))
BACKUP_KEY_FILE = Path(os.getenv("HPC_BACKUP_KEY_FILE", DATA_DIR.parent / "keys" / "backup.key"))


def _cloud_roots() -> list:
    """The folders Windows syncs to OneDrive (it sets these variables for each signed-in account)."""
    return [v for k, v in os.environ.items() if k.lower() in ("onedrive", "onedriveconsumer", "onedrivecommercial") and v]


def inside_cloud_folder(path, roots=None) -> bool:
    """Whether path is inside a synced folder (by where it is, not by what it is called)."""
    target = Path(path).resolve()
    for root in _cloud_roots() if roots is None else roots:
        try:
            target.relative_to(Path(root).resolve())
            return True
        except ValueError:
            continue
    return False


if any(inside_cloud_folder(p) for p in (DATA_DIR, BACKUP_DIR)):
    print(f"[config] WARNING: data or backups are inside OneDrive ({DATA_DIR}, {BACKUP_DIR}). "
          "Set HPC_DATA_DIR and HPC_BACKUP_DIR in .env to a folder that is not synced.")
for d in (DATA_DIR, SESSIONS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _jwt_secret() -> str:
    """HPC_JWT_SECRET if set, otherwise a random secret generated once and kept in data/."""
    if os.getenv("HPC_JWT_SECRET"):
        return os.environ["HPC_JWT_SECRET"]
    path = DATA_DIR / ".jwt_secret"
    if not path.exists():
        import secrets
        path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


JWT_SECRET = _jwt_secret()
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24              # legacy Bearer token in the login response: 24 hours (M-2)
# The legacy Bearer login ends after this day (M-2): no new Bearer tokens, and old ones are refused.
BEARER_LAST_DAY = date.fromisoformat(os.getenv("HPC_BEARER_LAST_DAY", "2026-11-01"))
ACCESS_COOKIE_MINUTES = 15                        # cookie session: short access token...
REFRESH_DAYS_DEFAULT, REFRESH_DAYS_REMEMBER = 1, 30   # ...renewed by a refresh token
COOKIE_SECURE = os.getenv("HPC_COOKIE_SECURE", "false").lower() == "true"   # set true behind HTTPS

# PARAKH login captcha. By default the teacher types it (the app shows PARAKH's picture).
# HPC_AUTO_CAPTCHA=true makes the app read the captcha itself: UNSUPPORTED, off by default,
# and to be removed before any paid launch (PARAKH has not approved automated logins).
AUTO_CAPTCHA = os.getenv("HPC_AUTO_CAPTCHA", "false").lower() == "true"

# Uploaded workbooks (students' data) are deleted after this many days; 0 keeps them (L-12).
UPLOAD_KEEP_DAYS = int(os.getenv("HPC_UPLOAD_KEEP_DAYS", "30"))

# The application admin (one account above every school): its login ID. The password is set once, on first
# sign-in, from a browser on the server PC itself; it is stored only as a hash.
APP_ADMIN_LOGIN = os.getenv("HPC_APP_ADMIN_LOGIN", "").strip().lower()

# Largest workbook a teacher may upload (M-6).
MAX_UPLOAD_BYTES = int(float(os.getenv("HPC_MAX_UPLOAD_MB", "20")) * 1024 * 1024)

# At most this many requests per second to PARAKH from one portal login (M-3: 1.5 unless .env says otherwise).
DEFAULT_PORTAL_MAX_PER_SECOND = 1.5
PORTAL_MAX_PER_SECOND = float(os.getenv("HPC_PORTAL_MAX_PER_SECOND", str(DEFAULT_PORTAL_MAX_PER_SECOND)))
