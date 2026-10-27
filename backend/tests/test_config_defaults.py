"""Safe defaults when .env leaves a setting out (M-3, M-4, M-6)."""
import json
from pathlib import Path


def test_parakh_is_asked_at_most_1_5_times_a_second_by_default():
    from backend import config
    assert config.DEFAULT_PORTAL_MAX_PER_SECOND == 1.5
    example = (Path(config.PROJECT_ROOT) / ".env.example").read_text(encoding="utf-8")
    assert "default 1.5" in example
