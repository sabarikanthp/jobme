from pathlib import Path

from jobme.config import paths


def test_data_dir_env_expands_user(monkeypatch):
    monkeypatch.setenv("JOBME_DATA_DIR", "~/JM")
    assert paths.data_dir() == Path.home() / "JM"


def test_saved_location_expands_user(monkeypatch):
    monkeypatch.delenv("JOBME_DATA_DIR", raising=False)
    paths.set_data_dir(Path("~/Saved"))
    assert paths.data_dir() == Path.home() / "Saved"


def test_location_file_is_isolated(tmp_path):
    assert tmp_path in paths._location_file().parents
