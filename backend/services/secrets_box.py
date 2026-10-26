"""
Encryption at rest for stored passwords (portal logins, teacher handover passwords).

Values are stored as "enc:v1:<Fernet token>". The key comes from HPC_SECRET_KEY, or is
generated once into data/.secret_key. Losing that key means the stored portal passwords
cannot be read any more (users would have to enter them again) - back it up with the data.
"""
import os

from cryptography.fernet import Fernet, InvalidToken

from backend.config import DATA_DIR

PREFIX = "enc:v1:"


def _key() -> bytes:
    if os.getenv("HPC_SECRET_KEY"):
        return os.environ["HPC_SECRET_KEY"].encode()
    path = DATA_DIR / ".secret_key"
    if not path.exists():
        path.write_bytes(Fernet.generate_key())
    return path.read_bytes().strip()


_fernet = Fernet(_key())


def encrypt(value: str | None) -> str | None:
    if value in (None, ""):
        return value
    if value.startswith(PREFIX):
        return value
    return PREFIX + _fernet.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value: str | None) -> str | None:
    """Plain text from before encryption was added is returned as it is."""
    if not value or not value.startswith(PREFIX):
        return value
    try:
        return _fernet.decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        return None


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)
