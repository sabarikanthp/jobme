import subprocess
from datetime import datetime, timezone

import pytest
from sqlmodel import Session

from jobme.config.settings import load_settings
from jobme.db.models import Run
from jobme.scheduling import windows_task as wt

UNSUPPORTED = "Scheduling from JobMe works on Windows. See docs/scheduling-mac-linux.md."
LISTING = "Scheduled Task State:  Enabled\nNext Run Time:  11/14/2026 7:30:00 AM\n"


class Fake:
    """A pretend schtasks that remembers whether the task exists."""

    def __init__(self):
        self.calls = []
        self.exists = False
        self.fail = None  # (returncode, stderr) for create

    def __call__(self, args):
        self.calls.append(list(args))
        verb = args[1]
        if verb == "/create":
            if self.fail:
                return subprocess.CompletedProcess(args, self.fail[0], "", self.fail[1])
            self.exists = True
            with open(args[args.index("/xml") + 1], "rb") as f:
                self.xml = f.read().decode("utf-16")
            return subprocess.CompletedProcess(args, 0, "", "")
        if verb == "/delete":
            if not self.exists:
                return subprocess.CompletedProcess(args, 1, "", "ERROR: The system cannot find the file specified.")
            self.exists = False
            return subprocess.CompletedProcess(args, 0, "", "")
        if self.exists:
            return subprocess.CompletedProcess(args, 0, LISTING, "")
        return subprocess.CompletedProcess(args, 1, "", "ERROR: The system cannot find the file specified.")

    def creates(self):
        return [c for c in self.calls if c[1] == "/create"]


@pytest.fixture
def sched(client, monkeypatch):
    monkeypatch.setattr(wt, "supported", lambda: True)
    fake = Fake()
    client.app.state.schedule_runner = fake
    return client, fake


BODY = {"days": ["mon", "fri"], "times": ["07:30"], "wake": True}


def test_turn_on_registers_and_the_status_reflects_it(sched):
    c, fake = sched
    before = c.get("/api/schedule").json()
    assert before["supported"] is True and before["enabled"] is False and before["last_run"] is None
    r = c.post("/api/schedule/on", json=BODY)
    assert r.status_code == 200, r.text
    assert len(fake.creates()) == 1
    after = c.get("/api/schedule").json()
    assert after["enabled"] is True and after["next_run"] == "11/14/2026 7:30:00 AM"
    assert (after["days"], after["times"], after["wake"]) == (["mon", "fri"], ["07:30"], True)
    assert load_settings(c.app.state.data_dir).schedule.enabled is True


def test_turning_on_again_replaces_the_task(sched):
    c, fake = sched
    c.post("/api/schedule/on", json=BODY)
    c.post("/api/schedule/on", json={**BODY, "times": ["08:00", "17:00"]})
    assert len(fake.creates()) == 2
    assert c.get("/api/schedule").json()["times"] == ["08:00", "17:00"]


def test_turn_off_removes_the_task(sched):
    c, fake = sched
    c.post("/api/schedule/on", json=BODY)
    r = c.post("/api/schedule/off")
    assert r.status_code == 200
    out = c.get("/api/schedule").json()
    assert out["enabled"] is False
    assert load_settings(c.app.state.data_dir).schedule.enabled is False
    assert c.post("/api/schedule/off").status_code == 200  # already off is fine


@pytest.mark.parametrize("body,copy", [
    ({"days": [], "times": ["07:30"]}, "Choose at least one day."),
    ({"days": ["mon"], "times": []}, "Choose at least one time."),
    ({"days": ["mon"], "times": ["7:30"]}, "Enter times like 07:30."),
    ({"days": ["mon"], "times": ["25:00"]}, "Enter times like 07:30."),
    ({"days": ["funday"], "times": ["07:30"]}, "Choose at least one day."),
])
def test_invalid_schedules_are_refused_and_nothing_is_registered(sched, body, copy):
    c, fake = sched
    r = c.post("/api/schedule/on", json=body)
    assert r.status_code == 400 and r.json()["detail"] == copy
    assert fake.calls == []
    assert load_settings(c.app.state.data_dir).schedule.enabled is False


def test_a_failing_scheduler_leaves_the_setting_off_and_shows_the_copy(sched):
    c, fake = sched
    fake.fail = (1, "ERROR: Access is denied.")
    r = c.post("/api/schedule/on", json=BODY)
    assert r.status_code == 400
    assert r.json()["detail"] == "Windows would not create the task. ERROR: Access is denied."
    assert load_settings(c.app.state.data_dir).schedule.enabled is False
    assert c.get("/api/schedule").json()["enabled"] is False  # the truth comes from the OS


def test_the_real_state_wins_over_a_saved_flag(sched):
    c, fake = sched
    c.post("/api/schedule/on", json=BODY)
    fake.exists = False  # someone removed the task in Task Scheduler
    assert c.get("/api/schedule").json()["enabled"] is False


def test_last_run_is_the_newest_scheduled_run_and_ignores_manual_ones(sched):
    c, _ = sched
    with Session(c.app.state.engine) as s:
        s.add(Run(trigger="schedule", started_at=datetime(2026, 11, 12, 6, tzinfo=timezone.utc),
                  finished_at=datetime(2026, 11, 12, 6, 5, tzinfo=timezone.utc), found=9, new=4, matched=2))
        s.add(Run(trigger="schedule", started_at=datetime(2026, 11, 13, 6, tzinfo=timezone.utc),
                  finished_at=datetime(2026, 11, 13, 6, 1, tzinfo=timezone.utc), errors=["No key"]))
        s.add(Run(trigger="manual", started_at=datetime(2026, 11, 14, 6, tzinfo=timezone.utc)))
        s.commit()
    last = c.get("/api/schedule").json()["last_run"]
    assert last["errors"] == ["No key"] and last["found"] == 0
    assert last["started_at"].startswith("2026-11-13")


def test_not_windows_reports_unsupported_and_refuses_to_turn_on(client, monkeypatch):
    monkeypatch.setattr(wt, "supported", lambda: False)
    client.app.state.schedule_runner = Fake()
    out = client.get("/api/schedule").json()
    assert out["supported"] is False and out["enabled"] is False
    r = client.post("/api/schedule/on", json=BODY)
    assert r.status_code == 400 and r.json()["detail"] == UNSUPPORTED
    assert client.post("/api/schedule/off").status_code == 400
    assert load_settings(client.app.state.data_dir).schedule.enabled is False


def test_the_command_in_the_task_has_no_secrets(sched):
    c, fake = sched
    c.post("/api/schedule/on", json=BODY)
    flat = " ".join(" ".join(call) for call in fake.calls).lower()
    assert "key" not in flat and "password" not in flat


def test_the_task_is_pointed_at_this_servers_data_folder(sched):
    c, fake = sched
    c.post("/api/schedule/on", json=BODY)
    assert str(c.app.state.data_dir) in fake.xml
    assert "--data-dir" in fake.xml
