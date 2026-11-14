"""The Windows scheduled task that runs `jobme run` unattended.

The task runs as the current user, only while that user is logged on, and stores no password:
the saved API keys live in the user's own Windows login and cannot be read any other way.
"""

import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

TASK_NAME = "JobMe daily search"
NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
START_DATE = "2026-01-01"  # only the time of day matters; the trigger repeats weekly
DAYS_COPY = "Choose at least one day."
TIMES_COPY = "Choose at least one time."
BAD_TIME_COPY = "Enter times like 07:30."

_WEEK = (
    ("mon", "Monday"), ("tue", "Tuesday"), ("wed", "Wednesday"), ("thu", "Thursday"),
    ("fri", "Friday"), ("sat", "Saturday"), ("sun", "Sunday"),
)
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

ET.register_namespace("", NAMESPACE)


def run_command(data_dir: str | None = None) -> tuple[str, str]:
    """pythonw.exe next to the running interpreter, so no console window opens.

    The data folder is passed explicitly, so the task and the screen you use always share one.
    """
    here = Path(sys.executable)
    windowless = here.with_name("pythonw.exe")
    command = windowless if windowless.exists() else here
    arguments = "-m jobme.cli run"
    if data_dir:
        arguments += f' --data-dir "{data_dir}"'
    return str(command), arguments


def _q(tag: str) -> str:
    return f"{{{NAMESPACE}}}{tag}"


def _add(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    element = ET.SubElement(parent, _q(tag))
    if text is not None:
        element.text = text
    return element


def build_task_xml(days: list[str], times: list[str], command: str, arguments: str, wake: bool) -> str:
    chosen = [name for key, name in _WEEK if key in days]
    if not chosen:
        raise ValueError(DAYS_COPY)
    if not times:
        raise ValueError(TIMES_COPY)
    if any(not _TIME.match(t) for t in times):
        raise ValueError(BAD_TIME_COPY)

    root = ET.Element(_q("Task"), {"version": "1.2"})
    info = _add(root, "RegistrationInfo")
    _add(info, "Description", "Runs the JobMe search on the days and times chosen in JobMe Settings.")

    triggers = _add(root, "Triggers")
    for time in times:
        trigger = _add(triggers, "CalendarTrigger")
        _add(trigger, "StartBoundary", f"{START_DATE}T{time}:00")
        _add(trigger, "Enabled", "true")
        week = _add(trigger, "ScheduleByWeek")
        _add(week, "WeeksInterval", "1")
        day_list = _add(week, "DaysOfWeek")
        for name in chosen:
            _add(day_list, name)

    principals = _add(root, "Principals")
    principal = ET.SubElement(principals, _q("Principal"), {"id": "Author"})
    _add(principal, "LogonType", "InteractiveToken")
    _add(principal, "RunLevel", "LeastPrivilege")

    settings = _add(root, "Settings")
    _add(settings, "MultipleInstancesPolicy", "IgnoreNew")
    _add(settings, "DisallowStartIfOnBatteries", "false")
    _add(settings, "StopIfGoingOnBatteries", "false")
    _add(settings, "StartWhenAvailable", "true")
    _add(settings, "WakeToRun", "true" if wake else "false")
    _add(settings, "ExecutionTimeLimit", "PT2H")
    _add(settings, "Hidden", "true")

    actions = ET.SubElement(root, _q("Actions"), {"Context": "Author"})
    action = _add(actions, "Exec")
    _add(action, "Command", command)
    _add(action, "Arguments", arguments)
    return ET.tostring(root, encoding="unicode")


# ------------------------------------------------------------ talking to schtasks

UNSUPPORTED_COPY = "Scheduling from JobMe works on Windows. See docs/scheduling-mac-linux.md."
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SCHTASKS_TIMEOUT = 30  # seconds


class SchedulerError(Exception):
    """The task could not be changed; the message is plain copy for the user."""


Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def default_runner(args: list[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(args, capture_output=True, text=True, timeout=SCHTASKS_TIMEOUT,
                          creationflags=NO_WINDOW)


def supported() -> bool:
    return sys.platform == "win32"


def _detail(proc: "subprocess.CompletedProcess[str]") -> str:
    for text in (proc.stderr, proc.stdout):
        for line in (text or "").splitlines():
            if line.strip():
                return line.strip()
    return ""


def _said(prefix: str, detail: str) -> str:
    return f"{prefix} {detail}".strip()


def register(xml: str, runner: Runner = default_runner) -> None:
    """Create the task, or replace it if it is already there."""
    if not supported():
        raise SchedulerError(UNSUPPORTED_COPY)
    prefix = "Windows would not create the task."
    handle, path = tempfile.mkstemp(suffix=".xml")
    os.close(handle)
    try:
        with open(path, "w", encoding="utf-16") as f:  # schtasks wants UTF-16 with a byte order mark
            f.write(xml)
        try:
            proc = runner(["schtasks", "/create", "/tn", TASK_NAME, "/xml", path, "/f"])
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SchedulerError(prefix) from exc
        if proc.returncode != 0:
            raise SchedulerError(_said(prefix, _detail(proc)))
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def unregister(runner: Runner = default_runner) -> None:
    if not supported():
        raise SchedulerError(UNSUPPORTED_COPY)
    prefix = "Windows would not remove the task."
    try:
        proc = runner(["schtasks", "/delete", "/tn", TASK_NAME, "/f"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SchedulerError(prefix) from exc
    if proc.returncode == 0:
        return
    said = f"{proc.stderr or ''}{proc.stdout or ''}".lower()
    if "cannot find" in said or "does not exist" in said:
        return  # already off
    raise SchedulerError(_said(prefix, _detail(proc)))


def status(runner: Runner = default_runner) -> dict:
    """What Windows says about the task: whether it is there and enabled, and its next run."""
    off = {"supported": supported(), "enabled": False, "next_run": None}
    if not supported():
        return off
    try:
        proc = runner(["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST", "/v"])
    except (OSError, subprocess.TimeoutExpired):
        return off
    if proc.returncode != 0:
        return off
    fields = {}
    for line in (proc.stdout or "").splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields.setdefault(key.strip().lower(), value.strip())
    enabled = fields.get("scheduled task state", "enabled").lower() == "enabled"
    next_run = fields.get("next run time") or None
    if next_run and next_run.upper() == "N/A":
        next_run = None
    return {"supported": True, "enabled": enabled, "next_run": next_run if enabled else None}
