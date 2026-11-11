"""Settings read the new KARTOUCHE_ names, and still honour the pre-rename
ROSETTA_ names so an existing deployment keeps working until it's updated."""

import importlib
from pathlib import Path

import config
import translate


def test_data_dir_prefers_new_name_and_falls_back(monkeypatch, tmp_path):
    monkeypatch.delenv("KARTOUCHE_DATA_DIR", raising=False)
    monkeypatch.setenv("ROSETTA_DATA_DIR", str(tmp_path / "old"))
    assert config.Settings().data_dir == Path(tmp_path / "old")
    monkeypatch.setenv("KARTOUCHE_DATA_DIR", str(tmp_path / "new"))
    assert config.Settings().data_dir == Path(tmp_path / "new")


def test_model_prefers_new_name_and_falls_back(monkeypatch):
    try:
        monkeypatch.delenv("KARTOUCHE_OPENAI_MODEL", raising=False)
        monkeypatch.setenv("ROSETTA_OPENAI_MODEL", "old-model")
        assert importlib.reload(translate).DEFAULT_MODEL == "old-model"
        monkeypatch.setenv("KARTOUCHE_OPENAI_MODEL", "new-model")
        assert importlib.reload(translate).DEFAULT_MODEL == "new-model"
        monkeypatch.delenv("KARTOUCHE_OPENAI_MODEL")
        monkeypatch.delenv("ROSETTA_OPENAI_MODEL")
        assert importlib.reload(translate).DEFAULT_MODEL == "gpt-4o"
    finally:
        monkeypatch.undo()
        importlib.reload(translate)
