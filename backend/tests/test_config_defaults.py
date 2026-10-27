"""Safe defaults when .env leaves a setting out (M-3, M-4, M-6)."""
from pathlib import Path


def test_parakh_is_asked_at_most_1_5_times_a_second_by_default():
    from backend import config
    assert config.DEFAULT_PORTAL_MAX_PER_SECOND == 1.5
    example = (Path(config.PROJECT_ROOT) / ".env.example").read_text(encoding="utf-8")
    assert "default 1.5" in example


def test_the_web_app_dev_server_listens_only_on_this_computer_unless_asked():
    from backend import config
    vite = (Path(config.PROJECT_ROOT) / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert "host: env.VITE_HOST || '127.0.0.1'" in vite and "'0.0.0.0'" not in vite
    example = (Path(config.PROJECT_ROOT) / "frontend" / ".env.example").read_text(encoding="utf-8")
    assert "VITE_HOST" in example
