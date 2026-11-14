import threading
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from jobme.agents.jobscout.pipeline import start_run
from jobme.api.app import create_app
from jobme.config import paths
from jobme.config.settings import Settings, load_settings, save_settings
from jobme.jobs.runlock import release_run_lock


def _put(client, data_dir, apps=...):
    """apps=... omits the field (what the UI sends when untouched)."""
    body = {"data_dir": str(data_dir)}
    if apps is not ...:
        body["applications_dir"] = apps
    return client.put("/api/storage", json=body)


def test_copy_to_new_folder(client, data_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("JOBME_DATA_DIR")
    client.put("/api/profile/user", json={"name": "Jordan Example"})
    target = tmp_path / "new"
    r = client.put("/api/storage", json={"data_dir": str(target), "applications_dir": None})
    assert r.status_code == 200 and r.json()["message"].startswith("Copied")
    assert (target / "profile" / "user.yaml").exists() and (data_dir / "profile" / "user.yaml").exists()
    assert (target / "jobme.db").exists()
    assert client.get("/api/profile/user").json()["name"] == "Jordan Example"
    assert paths.data_dir() == target


def test_adopts_existing_jobme_folder(client, tmp_path, monkeypatch):
    monkeypatch.delenv("JOBME_DATA_DIR")
    other = tmp_path / "restore"
    other.mkdir()
    save_settings(other, Settings(match_cutoff=60))
    r = client.put("/api/storage", json={"data_dir": str(other), "applications_dir": None})
    assert r.json()["message"] == "Using the JobMe data already in that folder."
    assert load_settings(other).match_cutoff == 60
    assert client.get("/api/storage").json()["data_dir"] == str(other)


def test_rejects_relative_and_nested(client, data_dir, monkeypatch):
    monkeypatch.delenv("JOBME_DATA_DIR")
    r = client.put("/api/storage", json={"data_dir": "JobMe", "applications_dir": None})
    assert r.status_code == 400
    assert r.json()["detail"].startswith("Please enter a full folder path")
    r = _put(client, data_dir / "inner")
    assert r.status_code == 400
    assert r.json()["detail"] == "Pick a folder that isn't inside the current data folder."
    r = _put(client, data_dir.parent)
    assert r.json()["detail"] == "Pick a folder that isn't inside the current data folder."


def test_unchanged_and_applications_dir(client, data_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("JOBME_DATA_DIR")
    apps = tmp_path / "apps"
    r = _put(client, data_dir, str(apps))
    assert r.status_code == 200
    assert r.json()["applications_dir"] == str(apps) and apps.is_dir()
    assert load_settings(data_dir).applications_dir == str(apps)
    assert _put(client, data_dir, "rel/apps").status_code == 400
    r = _put(client, data_dir, "")
    assert r.json()["applications_dir"] == str(data_dir / "applications")
    assert load_settings(data_dir).applications_dir is None


def test_locked_by_env(data_dir):  # env var left set
    with TestClient(create_app(data_dir)) as c:
        assert c.get("/api/storage").json()["locked"] is True
        r = c.put("/api/storage", json={"data_dir": str(data_dir.parent / "x"), "applications_dir": None})
        assert r.status_code == 409
        assert _put(c, data_dir).status_code == 200


def test_failed_copy_leaves_nothing_adoptable(client, data_dir, tmp_path, monkeypatch):
    import shutil

    monkeypatch.delenv("JOBME_DATA_DIR")
    client.put("/api/profile/user", json={"name": "Jordan Example"})
    target = tmp_path / "new"
    real = shutil.copy2

    def boom(src, dst, *a, **k):
        if "jobme.db" in str(src):
            raise OSError("disk full")
        return real(src, dst, *a, **k)

    with monkeypatch.context() as m:
        m.setattr(shutil, "copy2", boom)
        r = _put(client, target)
    assert r.status_code == 400
    assert not (target / "settings.yaml").exists()
    assert client.get("/api/storage").json()["data_dir"] == str(data_dir)
    assert client.get("/api/profile/user").json()["name"] == "Jordan Example"
    assert _put(client, target).json()["message"].startswith("Copied")


def test_adopt_keeps_saved_applications_dir(client, tmp_path, monkeypatch):
    monkeypatch.delenv("JOBME_DATA_DIR")
    other = tmp_path / "restore"
    other.mkdir()
    apps = tmp_path / "myapps"
    save_settings(other, Settings(applications_dir=str(apps)))
    r = _put(client, other)
    assert r.json()["applications_dir"] == str(apps)
    assert load_settings(other).applications_dir == str(apps)


def test_adopt_invalid_settings_switches_nothing(client, data_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("JOBME_DATA_DIR")
    other = tmp_path / "bad"
    other.mkdir()
    (other / "settings.yaml").write_text("match_cutoff: 500\n", encoding="utf-8")
    r = _put(client, other)
    assert r.status_code == 400
    assert client.get("/api/storage").json()["data_dir"] == str(data_dir)
    assert paths.data_dir() != other


def test_failed_copy_keeps_preexisting_target_files(client, data_dir, tmp_path, monkeypatch):
    import shutil

    monkeypatch.delenv("JOBME_DATA_DIR")
    target = tmp_path / "new"
    target.mkdir()
    (target / "jobme.db").write_bytes(b"original")
    real = shutil.copy2

    def boom(src, dst, *a, **k):
        if str(src).endswith("settings.yaml"):
            raise OSError("disk full")
        return real(src, dst, *a, **k)

    with monkeypatch.context() as m:
        m.setattr(shutil, "copy2", boom)
        assert _put(client, target).status_code == 400
    assert (target / "jobme.db").read_bytes() == b"original"


def test_invalid_current_settings_copies_nothing(client, data_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("JOBME_DATA_DIR")
    (data_dir / "settings.yaml").write_text("match_cutoff: 500" + chr(10), encoding="utf-8")
    target = tmp_path / "new"
    assert _put(client, target).status_code == 400
    assert not (target / "settings.yaml").exists() and not (target / "jobme.db").exists()


def test_adopt_omitted_field_keeps_adopted_default(client, tmp_path, monkeypatch):
    monkeypatch.delenv("JOBME_DATA_DIR")
    other = tmp_path / "restore"
    other.mkdir()
    save_settings(other, Settings())
    r = _put(client, other)
    assert r.status_code == 200
    assert load_settings(other).applications_dir is None
    assert r.json()["applications_dir"] == str(other.resolve() / "applications")


def test_copy_omitted_field_keeps_default_following_new_folder(client, tmp_path, monkeypatch):
    monkeypatch.delenv("JOBME_DATA_DIR")
    target = tmp_path / "new"
    r = _put(client, target)
    assert r.json()["message"].startswith("Copied")
    assert load_settings(target).applications_dir is None
    assert r.json()["applications_dir"] == str(target.resolve() / "applications")


def test_unchanged_omitted_field_keeps_custom_value(client, data_dir, tmp_path):
    apps = tmp_path / "apps"
    _put(client, data_dir, str(apps))
    r = _put(client, data_dir)
    assert r.json()["applications_dir"] == str(apps)
    assert load_settings(data_dir).applications_dir == str(apps)


def test_empty_string_resets_and_new_value_sets(client, data_dir, tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    _put(client, data_dir, str(first))
    assert _put(client, data_dir, str(second)).json()["applications_dir"] == str(second)
    assert load_settings(data_dir).applications_dir == str(second)
    assert _put(client, data_dir, "").json()["applications_dir"] == str(data_dir / "applications")
    assert load_settings(data_dir).applications_dir is None


def test_folder_change_refused_during_run(client, data_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("JOBME_DATA_DIR")
    target = tmp_path / "new"
    engine = client.app.state.engine
    start_run(engine, "manual", datetime.now(timezone.utc))
    r = _put(client, target)
    assert r.status_code == 409 and r.json()["detail"] == "A run is already in progress."
    assert not target.exists() and client.app.state.engine is engine
    release_run_lock(engine)

    done = threading.Event()
    thread = threading.Thread(target=done.wait)
    thread.start()
    client.app.state.run_thread = thread
    try:
        assert _put(client, target).status_code == 409 and not target.exists()
    finally:
        done.set()
        thread.join()
    assert _put(client, target).status_code == 200
