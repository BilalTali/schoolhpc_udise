"""
Encrypts a whole folder into one archive with the backup key, then proves it: decrypts the archive
again and checks every file's SHA-256 against the original. Nothing unencrypted is written to disk.

    python scripts/encrypt_folder.py <folder> <archive.taenc>      encrypt + verify
    python scripts/encrypt_folder.py --extract <archive.taenc> <target folder>

Format: b"TAENC1\\n", then pieces: 4-byte big-endian length + Fernet token of up to 16 MB of a
.tar.gz stream. Fernet = AES-128-CBC + HMAC-SHA256, so a changed byte is detected.
"""
import hashlib
import io
import struct
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backup_db import backup_key  # noqa: E402

MAGIC = b"TAENC1\n"
PIECE = 16 * 1024 * 1024


class EncryptingWriter(io.RawIOBase):
    """A file-like object tarfile writes into; every 16 MB is encrypted and appended to the archive."""

    def __init__(self, out, box):
        self.out, self.box, self.buf = out, box, bytearray()
        out.write(MAGIC)

    def writable(self):
        return True

    def write(self, b):
        self.buf += b
        while len(self.buf) >= PIECE:
            self._emit(bytes(self.buf[:PIECE]))
            del self.buf[:PIECE]
        return len(b)

    def _emit(self, chunk):
        token = self.box.encrypt(chunk)
        self.out.write(struct.pack(">I", len(token)) + token)

    def close(self):
        if self.buf:
            self._emit(bytes(self.buf))
            self.buf = bytearray()
        super().close()


class DecryptingReader(io.RawIOBase):
    def __init__(self, path, box):
        self.f, self.box, self.buf = open(path, "rb"), box, b""
        if self.f.read(len(MAGIC)) != MAGIC:
            raise SystemExit("not an archive made by encrypt_folder.py")

    def readable(self):
        return True

    def readinto(self, target):
        while not self.buf:
            head = self.f.read(4)
            if not head:
                return 0
            self.buf = self.box.decrypt(self.f.read(struct.unpack(">I", head)[0]))
        n = min(len(target), len(self.buf))
        target[:n], self.buf = self.buf[:n], self.buf[n:]
        return n


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def encrypt(folder: Path, archive: Path) -> dict:
    box = backup_key()
    expected = {}
    archive.parent.mkdir(parents=True, exist_ok=True)
    with open(archive, "wb") as out:
        writer = EncryptingWriter(out, box)
        with tarfile.open(fileobj=writer, mode="w|gz") as tar:
            for p in sorted(folder.rglob("*")):
                if p.is_file():
                    rel = p.relative_to(folder).as_posix()
                    expected[rel] = sha(p)
                    tar.add(p, arcname=rel, recursive=False)
        writer.close()
    return expected


def verify(archive: Path, expected: dict) -> list:
    box = backup_key()
    seen, problems = {}, []
    with tarfile.open(fileobj=io.BufferedReader(DecryptingReader(archive, box)), mode="r|gz") as tar:
        for m in tar:
            if m.isfile():
                h = hashlib.sha256()
                f = tar.extractfile(m)
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
                seen[m.name] = h.hexdigest()
    for rel, digest in expected.items():
        if seen.get(rel) != digest:
            problems.append(rel)
    problems += [rel for rel in seen if rel not in expected]
    return problems


def main() -> int:
    if sys.argv[1] == "--extract":
        archive, target = Path(sys.argv[2]), Path(sys.argv[3])
        with tarfile.open(fileobj=io.BufferedReader(DecryptingReader(archive, backup_key())), mode="r|gz") as tar:
            tar.extractall(target, filter="data")
        print(f"extracted into {target}")
        return 0
    folder, archive = Path(sys.argv[1]), Path(sys.argv[2])
    expected = encrypt(folder, archive)
    problems = verify(archive, expected)
    size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
    print(f"{len(expected)} files ({size:,} bytes) -> {archive} ({archive.stat().st_size:,} bytes)")
    print(f"verify {'PASS' if not problems else 'FAIL'}: every file decrypted and matched its SHA-256"
          if not problems else f"verify FAIL: {len(problems)} file(s) differ, e.g. {problems[:3]}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
