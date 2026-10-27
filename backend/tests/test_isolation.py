"""The tests never touch the real data folder, keys or backups (finding A-01)."""
import tempfile
from pathlib import Path

REAL_ROOT = Path("C:/TeacherAssist").resolve()


def _inside(path, root) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def test_data_backups_and_keys_are_temporary_folders():
    from backend import config
    for path in (config.DATA_DIR, config.SESSIONS_DIR, config.BACKUP_DIR, config.BACKUP_KEY_FILE):
        assert not _inside(path, REAL_ROOT), f"tests point at the real folder: {path}"
        assert _inside(path, tempfile.gettempdir()), f"tests must use a temporary folder, not {path}"


def test_jwt_secret_and_encryption_key_are_made_for_the_tests():
    from backend import config
    from backend.services import secrets_box
    assert (config.DATA_DIR / ".jwt_secret").read_text(encoding="utf-8").strip() == config.JWT_SECRET
    assert (config.DATA_DIR / ".secret_key").read_bytes().strip() == secrets_box._key()
    real = REAL_ROOT / "data"
    for name in (".jwt_secret", ".secret_key"):
        if (real / name).exists():
            assert (real / name).read_bytes().strip() != (config.DATA_DIR / name).read_bytes().strip()


def test_onedrive_warning_checks_where_the_folder_is_not_its_name(tmp_path):
    # A-02: a folder whose *name* contains "OneDrive" is not inside OneDrive
    from backend import config
    onedrive = tmp_path / "OneDrive"
    roots = [str(onedrive)]
    assert config.inside_cloud_folder(onedrive / "TeacherAssist" / "data", roots)
    assert config.inside_cloud_folder(onedrive, roots)
    assert not config.inside_cloud_folder(tmp_path / "c--Users-abdul-OneDrive-Desktop" / "data", roots)
    assert not config.inside_cloud_folder(tmp_path / "OneDriveBackup", roots)
    assert not config.inside_cloud_folder(tmp_path / "data", [])
