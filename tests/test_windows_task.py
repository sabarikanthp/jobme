import re
import xml.etree.ElementTree as ET

import pytest

from jobme.scheduling import windows_task as wt

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def build(days=("mon", "fri"), times=("07:30", "12:00"), wake=False, command="C:\\py\\pythonw.exe",
          arguments="-m jobme.cli run"):
    return wt.build_task_xml(list(days), list(times), command, arguments, wake)


def parse(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def test_xml_has_one_trigger_per_time_with_the_chosen_days():
    root = parse(build())
    triggers = root.findall("t:Triggers/t:CalendarTrigger", NS)
    assert [t.find("t:StartBoundary", NS).text for t in triggers] == ["2026-01-01T07:30:00", "2026-01-01T12:00:00"]
    for t in triggers:
        week = t.find("t:ScheduleByWeek", NS)
        assert week.find("t:WeeksInterval", NS).text == "1"
        assert [d.tag.split("}")[1] for d in week.find("t:DaysOfWeek", NS)] == ["Monday", "Friday"]
        assert t.find("t:Enabled", NS).text == "true"


def test_xml_settings_match_the_constraints():
    root = parse(build())
    st = root.find("t:Settings", NS)
    text = lambda name: st.find(f"t:{name}", NS).text
    assert text("StartWhenAvailable") == "true"
    assert text("WakeToRun") == "false"
    assert text("MultipleInstancesPolicy") == "IgnoreNew"
    assert text("DisallowStartIfOnBatteries") == "false"
    assert text("StopIfGoingOnBatteries") == "false"
    assert text("ExecutionTimeLimit") == "PT2H"
    assert text("Hidden") == "true"
    principal = root.find("t:Principals/t:Principal", NS)
    assert principal.find("t:LogonType", NS).text == "InteractiveToken"
    assert principal.find("t:RunLevel", NS).text == "LeastPrivilege"
    assert parse(build(wake=True)).find("t:Settings/t:WakeToRun", NS).text == "true"


def test_xml_has_one_exec_action_and_escapes_the_command_path():
    command = "C:\\Tom & Jerry\\pythonw.exe"
    root = parse(build(command=command))
    exec_ = root.findall("t:Actions/t:Exec", NS)
    assert len(exec_) == 1
    assert exec_[0].find("t:Command", NS).text == command
    assert exec_[0].find("t:Arguments", NS).text == "-m jobme.cli run"


def test_all_seven_days_are_known():
    root = parse(build(days=("mon", "tue", "wed", "thu", "fri", "sat", "sun")))
    days = root.find("t:Triggers/t:CalendarTrigger/t:ScheduleByWeek/t:DaysOfWeek", NS)
    assert [d.tag.split("}")[1] for d in days] == [
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def test_days_come_out_in_week_order_whatever_the_input_order():
    root = parse(build(days=("sun", "mon")))
    days = root.find("t:Triggers/t:CalendarTrigger/t:ScheduleByWeek/t:DaysOfWeek", NS)
    assert [d.tag.split("}")[1] for d in days] == ["Monday", "Sunday"]


def test_empty_days_or_times_raise_with_the_copy():
    with pytest.raises(ValueError, match="Choose at least one day."):
        build(days=())
    with pytest.raises(ValueError, match="Choose at least one time."):
        build(times=())


def test_a_bad_time_or_day_is_refused():
    with pytest.raises(ValueError, match="Enter times like 07:30."):
        build(times=("7:30",))
    with pytest.raises(ValueError, match="Enter times like 07:30."):
        build(times=("25:00",))
    with pytest.raises(ValueError, match="Choose at least one day."):
        build(days=("funday",))


def test_the_task_name_has_no_em_dash():
    assert wt.TASK_NAME == "JobMe daily search"
    assert "\u2014" not in build()


def test_the_xml_never_carries_a_secret_like_value():
    text = build()
    words = set(re.findall(r"[A-Za-z]+", re.sub(r"</?[A-Za-z]+", "", text))).copy()
    assert not {w.lower() for w in words} & {"password", "apikey", "secret", "token"}


def test_run_command_prefers_pythonw_next_to_the_interpreter(tmp_path, monkeypatch):
    (tmp_path / "python.exe").write_text("")
    (tmp_path / "pythonw.exe").write_text("")
    monkeypatch.setattr(wt.sys, "executable", str(tmp_path / "python.exe"))
    command, arguments = wt.run_command()
    assert command == str(tmp_path / "pythonw.exe")
    assert arguments == "-m jobme.cli run"


def test_run_command_falls_back_to_the_interpreter(tmp_path, monkeypatch):
    (tmp_path / "python.exe").write_text("")
    monkeypatch.setattr(wt.sys, "executable", str(tmp_path / "python.exe"))
    assert wt.run_command() == (str(tmp_path / "python.exe"), "-m jobme.cli run")


# ------------------------------------------------------------ register, remove, read

import os
import subprocess


class FakeScheduler:
    """Stands in for schtasks: records the arguments and reads the XML file while it exists."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.calls = []
        self.result = (returncode, stdout, stderr)
        self.xml_bytes = None
        self.xml_path = None

    def __call__(self, args):
        self.calls.append(list(args))
        if "/xml" in args:
            self.xml_path = args[args.index("/xml") + 1]
            with open(self.xml_path, "rb") as f:
                self.xml_bytes = f.read()
        code, out, err = self.result
        return subprocess.CompletedProcess(args, code, stdout=out, stderr=err)


@pytest.fixture
def on_windows(monkeypatch):
    monkeypatch.setattr(wt, "supported", lambda: True)


def test_register_writes_utf16_xml_and_calls_schtasks_create(on_windows):
    fake = FakeScheduler()
    wt.register(build(), fake)
    assert fake.calls == [["schtasks", "/create", "/tn", "JobMe daily search", "/xml", fake.xml_path, "/f"]]
    assert fake.xml_bytes[:2] in (b"\xff\xfe", b"\xfe\xff")  # a UTF-16 byte order mark
    assert parse(fake.xml_bytes.decode("utf-16")).tag.endswith("Task")
    assert not os.path.exists(fake.xml_path)


def test_register_failure_becomes_a_scheduler_error_with_copy(on_windows):
    fake = FakeScheduler(1, "", "ERROR: Access is denied.\r\nMore detail")
    with pytest.raises(wt.SchedulerError) as err:
        wt.register(build(), fake)
    assert str(err.value) == "Windows would not create the task. ERROR: Access is denied."


def test_a_missing_schtasks_program_is_a_scheduler_error(on_windows):
    def broken(args):
        raise FileNotFoundError("schtasks")

    with pytest.raises(wt.SchedulerError, match="Windows would not create the task."):
        wt.register(build(), broken)


def test_unregister_treats_a_missing_task_as_success(on_windows):
    fake = FakeScheduler(1, "", "ERROR: The system cannot find the file specified.")
    wt.unregister(fake)
    assert fake.calls == [["schtasks", "/delete", "/tn", "JobMe daily search", "/f"]]


def test_unregister_reports_other_failures(on_windows):
    with pytest.raises(wt.SchedulerError, match="Windows would not remove the task. ERROR: Access is denied."):
        wt.unregister(FakeScheduler(1, "", "ERROR: Access is denied."))


LISTING = """
Folder: \
HostName:                             PC
TaskName:                             \JobMe daily search
Next Run Time:                        11/14/2026 7:30:00 AM
Status:                               Ready
Scheduled Task State:                 Enabled
"""


def test_status_parses_enabled_and_next_run(on_windows):
    fake = FakeScheduler(0, LISTING)
    assert wt.status(fake) == {"supported": True, "enabled": True, "next_run": "11/14/2026 7:30:00 AM"}
    assert fake.calls == [["schtasks", "/query", "/tn", "JobMe daily search", "/fo", "LIST", "/v"]]


def test_status_of_a_disabled_task_and_of_no_next_run(on_windows):
    disabled = LISTING.replace("Enabled", "Disabled").replace("11/14/2026 7:30:00 AM", "N/A")
    assert wt.status(FakeScheduler(0, disabled)) == {"supported": True, "enabled": False, "next_run": None}


def test_status_for_a_missing_task(on_windows):
    out = wt.status(FakeScheduler(1, "", "ERROR: The system cannot find the file specified."))
    assert out == {"supported": True, "enabled": False, "next_run": None}


def test_not_windows_raises_the_unsupported_copy(monkeypatch):
    monkeypatch.setattr(wt, "supported", lambda: False)
    fake = FakeScheduler()
    with pytest.raises(wt.SchedulerError) as err:
        wt.register(build(), fake)
    assert str(err.value) == "Scheduling from JobMe works on Windows. See docs/scheduling-mac-linux.md."
    with pytest.raises(wt.SchedulerError):
        wt.unregister(fake)
    assert wt.status(fake) == {"supported": False, "enabled": False, "next_run": None}
    assert fake.calls == []


def test_run_command_can_point_the_task_at_the_data_folder(tmp_path, monkeypatch):
    (tmp_path / "python.exe").write_text("")
    monkeypatch.setattr(wt.sys, "executable", str(tmp_path / "python.exe"))
    _, arguments = wt.run_command("C:\Data Folder\JobMe")
    assert arguments == '-m jobme.cli run --data-dir "C:\Data Folder\JobMe"'
