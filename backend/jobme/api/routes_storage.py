import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jobme.config import paths, storage
from jobme.config.settings import Settings, SettingsError, load_settings, save_settings
from jobme.db.session import get_engine, init_db
from jobme.jobs.runlock import IN_PROGRESS_COPY, run_lock_held

router = APIRouter()

LOCKED = "The data folder is set by JOBME_DATA_DIR and can't be changed here."


class StorageIn(BaseModel):
    data_dir: str
    # Omitted or null = keep the saved value; "" = reset to the default; text = set it.
    applications_dir: str | None = None


def _view(data_dir: Path) -> dict:
    try:
        settings = load_settings(data_dir)
    except SettingsError:
        settings = Settings()
    return {
        "data_dir": str(data_dir),
        "applications_dir": str(settings.applications_path(data_dir)),
        "locked": bool(os.environ.get("JOBME_DATA_DIR")),
    }


def _run_in_progress(app) -> bool:
    thread = getattr(app.state, "run_thread", None)
    if thread is not None and thread.is_alive():
        return True
    return run_lock_held(app.state.engine, datetime.now(timezone.utc))


@router.get("/storage")
def get_storage(request: Request) -> dict:
    return _view(request.app.state.data_dir)


@router.put("/storage")
def put_storage(body: StorageIn, request: Request) -> dict:
    app = request.app
    current: Path = app.state.data_dir
    raw = Path(body.data_dir.strip()).expanduser()
    # Lock applies only when the folder would really change (checked before validation).
    if os.environ.get("JOBME_DATA_DIR") and raw.resolve() != current.resolve():
        raise HTTPException(409, LOCKED)
    # Moving the folder disposes the engine and copies jobme.db: never while a run writes to it.
    if raw.resolve() != current.resolve() and _run_in_progress(app):
        raise HTTPException(409, IN_PROGRESS_COPY)
    try:
        target = storage.parse_folder(body.data_dir)
        apps_in = body.applications_dir
        apps = storage.parse_folder(apps_in) if apps_in and apps_in.strip() else None
        storage.check_nesting(current, target)
        if storage.will_copy(current, target):
            load_settings(current)  # refuse before copying a settings file we can't read
            app.state.engine.dispose()  # release file locks before copying (Windows)
        result = storage.change_data_dir(current, target)
    except (storage.StorageError, SettingsError) as e:
        raise HTTPException(400, str(e)) from e

    messages = {
        "unchanged": "Saved.",
        "adopted": "Using the JobMe data already in that folder.",
        "copied": "Copied your JobMe data to the new folder. The old folder was left as it was.",
    }
    new_dir = target.resolve() if result != "unchanged" else current
    try:
        settings = load_settings(new_dir)
    except SettingsError as e:
        raise HTTPException(400, str(e)) from e
    if apps_in is not None:
        settings.applications_dir = str(apps) if apps else None
    if result != "unchanged":
        paths.set_data_dir(new_dir)
        old_engine = app.state.engine
        app.state.data_dir = new_dir
        app.state.engine = get_engine(new_dir)
        old_engine.dispose()
    data_dir: Path = app.state.data_dir
    save_settings(data_dir, settings)
    paths.ensure_dirs(data_dir, settings)
    init_db(app.state.engine)
    return {**_view(data_dir), "message": messages[result]}
