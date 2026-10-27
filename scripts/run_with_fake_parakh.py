"""
Starts the app against the fake PARAKH (scripts/fake_parakh.py) with a scratch database and data folder.
Every connection that is not to this computer is refused, so nothing can reach the real PARAKH.

    python scripts/run_with_fake_parakh.py <scratch folder> [app port] [fake PARAKH port]

The scratch folder gets app.db, data/, backups/ and keys/. Nothing from .env's data or database is used.
"""
import os
import socket
import sys
from pathlib import Path

scratch = Path(sys.argv[1]).resolve()
app_port = int(sys.argv[2]) if len(sys.argv) > 2 else 8001
fake_port = int(sys.argv[3]) if len(sys.argv) > 3 else 8765
scratch.mkdir(parents=True, exist_ok=True)
# set before backend.config loads .env (which only fills in what is not set)
os.environ.update({"HPC_DATABASE_URL": f"sqlite:///{(scratch / 'app.db').as_posix()}",
                   "HPC_DATA_DIR": str(scratch / "data"), "HPC_BACKUP_DIR": str(scratch / "backups"),
                   "HPC_BACKUP_KEY_FILE": str(scratch / "keys" / "backup.key"), "HPC_AUTO_CAPTCHA": "false"})

LOCAL = {"127.0.0.1", "::1", "localhost"}
_real_getaddrinfo, _real_connect = socket.getaddrinfo, socket.socket.connect


def _local_only_getaddrinfo(host, *args, **kwargs):
    if str(host) not in LOCAL:
        raise OSError(f"blocked: no outside connections while running against the fake PARAKH ({host})")
    return _real_getaddrinfo(host, *args, **kwargs)


def _local_only_connect(self, address):
    if isinstance(address, tuple) and str(address[0]) not in LOCAL:
        raise OSError(f"blocked: no outside connections while running against the fake PARAKH ({address[0]})")
    return _real_connect(self, address)


socket.getaddrinfo, socket.socket.connect = _local_only_getaddrinfo, _local_only_connect

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.hpc import portal  # noqa: E402

portal.BASE_URL = f"http://127.0.0.1:{fake_port}"
portal.API = f"{portal.BASE_URL}/api/proxy"

import uvicorn  # noqa: E402

uvicorn.run("backend.main:app", host="127.0.0.1", port=app_port, log_level="info")
