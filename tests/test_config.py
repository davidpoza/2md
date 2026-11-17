import json

import pytest
from pydantic import ValidationError

from twomd.config import Settings, load_settings, save_settings


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(output_directory="C:\\destino", document_concurrency=3)
    save_settings(path, settings)
    assert load_settings(path) == settings
    assert set(json.loads(path.read_text(encoding="utf-8"))) == {
        "output_directory",
        "document_concurrency",
        "ai",
        "network",
        "mcp",
    }


def test_legacy_models_directory_is_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"models_directory": "C:\\\\modelos"}', encoding="utf-8")
    settings = load_settings(path)
    save_settings(path, settings)
    assert "models_directory" not in json.loads(path.read_text(encoding="utf-8"))


def test_invalid_settings_are_not_silently_discarded(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"document_concurrency": 0}', encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(path)
    assert path.read_text(encoding="utf-8") == '{"document_concurrency": 0}'
