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
        "models_directory",
        "ai",
        "network",
    }


def test_invalid_settings_are_not_silently_discarded(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"document_concurrency": 0}', encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(path)
    assert path.read_text(encoding="utf-8") == '{"document_concurrency": 0}'
