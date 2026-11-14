import shutil
from pathlib import Path
from typing import Literal

NOT_INSIDE = "Pick a folder that isn't inside the current data folder."
NEEDS_FULL_PATH = r"Please enter a full folder path, for example C:\Users\you\JobMe."


class StorageError(Exception):
    pass


def parse_folder(text: str) -> Path:
    """Expand and require an absolute path."""
    path = Path(text.strip()).expanduser()
    if not path.is_absolute():
        raise StorageError(NEEDS_FULL_PATH)
    return path


def _is_inside(inner: Path, outer: Path) -> bool:
    return inner == outer or outer in inner.parents


def change_data_dir(current: Path, target: Path) -> Literal["unchanged", "adopted", "copied"]:
    """Copy or adopt data for a new folder. When `will_copy` is true the caller must
    dispose the current engine first (Windows file locks)."""
    current, target = current.resolve(), target.resolve()
    if current == target:
        return "unchanged"
    if _is_inside(target, current) or _is_inside(current, target):
        raise StorageError(NOT_INSIDE)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise StorageError(f"Couldn't create that folder: {e.strerror or e}") from e
    if (target / "settings.yaml").exists():
        return "adopted"
    created: list[Path] = []
    backups: list[tuple[Path, Path]] = []
    try:
        if (current / "profile").is_dir():
            profile_existed = (target / "profile").exists()
            if not profile_existed:
                created.append(target / "profile")
            shutil.copytree(current / "profile", target / "profile", dirs_exist_ok=True)
        # settings.yaml goes last: its presence marks a folder as complete.
        for name in ("jobme.db", "jobme.db-wal", "jobme.db-shm", "settings.yaml"):
            src = current / name
            if src.is_file():
                dest = target / name
                if dest.exists():
                    backup = dest.with_name(dest.name + ".jobme-backup")
                    shutil.copyfile(dest, backup)
                    backups.append((dest, backup))
                else:
                    created.append(dest)
                shutil.copy2(src, dest)
    except OSError as e:
        for dest, backup in backups:
            try:
                shutil.move(backup, dest)
            except OSError:
                pass
        for path in reversed(created):
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
            except OSError:
                pass
        raise StorageError(f"Couldn't create that folder: {e.strerror or e}") from e
    for _, backup in backups:
        backup.unlink(missing_ok=True)
    return "copied"


def check_nesting(current: Path, target: Path) -> None:
    current, target = current.resolve(), target.resolve()
    if current != target and (_is_inside(target, current) or _is_inside(current, target)):
        raise StorageError(NOT_INSIDE)


def will_copy(current: Path, target: Path) -> bool:
    return (
        current.resolve() != target.resolve() and not (target.resolve() / "settings.yaml").exists()
    )
