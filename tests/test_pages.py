import io
import subprocess

import docx
from docx_fixtures import make_resume_docx, set_app_pages

from jobme.applydocs.content import TailoredBullet, TailoredContent, TailoredRole
from jobme.applydocs.pages import fit_pages, original_page_count, word_page_counter


def texts(data):
    return [p.text for p in docx.Document(io.BytesIO(data)).paragraphs]


def fake_counter(pages_by_bullets):
    def count(data):
        return pages_by_bullets(sum(1 for t in texts(data) if t.startswith("B")))
    return count


def content(n):
    return TailoredContent(headline="", summary="S", skills=[], roles=[TailoredRole(role=0, bullets=[TailoredBullet(source=i, text=f"B{i}") for i in range(n)])])


def render_fn(c):
    d = docx.Document()
    for r in c.roles:
        for b in r.bullets:
            d.add_paragraph(b.text)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_drops_bullets_until_pages_match():
    r = fit_pages(render_fn, content(6), content(6), target=2, counter=fake_counter(lambda n: 3 if n > 4 else 2))
    assert r.pages == 2 and r.note == "2 pages, same as your resume" and len(r.content.roles[0].bullets) == 4


def test_puts_back_left_out_bullets_when_short():
    r = fit_pages(render_fn, content(2), content(5), target=2, counter=fake_counter(lambda n: 2 if n >= 4 else 1))
    assert r.pages == 2 and [b.source for b in r.content.roles[0].bullets] == [0, 1, 2, 3]


def test_word_missing_uses_estimate():
    long = content(3)
    long.roles[0].bullets[0].text = "B" + "x" * 400
    r = fit_pages(render_fn, long, content(3), target=2, counter=lambda data: None)
    assert r.note == "Couldn't confirm the page count" and r.content.roles[0].bullets[0].text == "B0"


def test_closest_when_cannot_match():
    r = fit_pages(render_fn, content(2), content(2), target=2, counter=fake_counter(lambda n: 1))
    assert r.pages == 1 and r.note == "1 page; your resume has 2. JobMe kept the closest version."


def test_original_page_count_and_word_counter_failure(monkeypatch):
    assert original_page_count(set_app_pages(make_resume_docx(), 2)) == 2
    monkeypatch.setattr("subprocess.run", lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("powershell", 90)))
    assert word_page_counter(make_resume_docx()) is None


def test_original_page_count_bad_input():
    assert original_page_count(b"not a zip") is None
    assert original_page_count(set_app_pages(make_resume_docx(), 0)) is None


def test_word_counter_passes_path_as_argument_and_parses(monkeypatch):
    calls = []

    def fake_run(args, **kw):
        calls.append((args, kw))
        return subprocess.CompletedProcess(args, 0, stdout="3\r\n", stderr="")

    monkeypatch.setattr("jobme.applydocs.pages.sys.platform", "win32")
    monkeypatch.setattr("subprocess.run", fake_run)
    assert word_page_counter(make_resume_docx()) == 3
    args, kw = calls[0]
    assert args[0] == "powershell.exe" and kw["timeout"] == 90
    assert args[-2].endswith(".docx") and args[-1].endswith(".pid") and "-File" in args


def test_word_counter_none_on_bad_output_or_exit(monkeypatch):
    monkeypatch.setattr("jobme.applydocs.pages.sys.platform", "win32")
    monkeypatch.setattr("subprocess.run", lambda a, **k: subprocess.CompletedProcess(a, 0, stdout="oops", stderr=""))
    assert word_page_counter(b"x") is None
    monkeypatch.setattr("subprocess.run", lambda a, **k: subprocess.CompletedProcess(a, 1, stdout="2", stderr=""))
    assert word_page_counter(b"x") is None
    monkeypatch.setattr("jobme.applydocs.pages.sys.platform", "linux")
    assert word_page_counter(b"x") is None


def _pid_file_of(args):
    return args[-1]


def _timeout_run(pid_text, calls):
    def fake_run(args, **kw):
        calls.append(args)
        if args[0] == "powershell.exe":
            if pid_text is not None:
                with open(_pid_file_of(args), "w") as f:
                    f.write(pid_text)
            raise subprocess.TimeoutExpired("powershell", 90)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
    return fake_run


def test_timeout_kills_exactly_the_recorded_word_pid(monkeypatch):
    calls = []
    monkeypatch.setattr("jobme.applydocs.pages.sys.platform", "win32")
    monkeypatch.setattr("subprocess.run", _timeout_run("4321\r\n", calls))
    assert word_page_counter(make_resume_docx()) is None
    kills = [c for c in calls if c[0] == "taskkill"]
    assert kills == [["taskkill", "/PID", "4321", "/F"]]


def test_unparsable_pid_file_never_reaches_taskkill(monkeypatch):
    for text in ("1234; calc", "abc", "-5", "0", None):
        calls = []
        monkeypatch.setattr("jobme.applydocs.pages.sys.platform", "win32")
        monkeypatch.setattr("subprocess.run", _timeout_run(text, calls))
        assert word_page_counter(make_resume_docx()) is None
        assert not [c for c in calls if c[0] == "taskkill"]


def test_word_script_is_hardened_and_path_free(monkeypatch):
    from jobme.applydocs.pages import WORD_SCRIPT
    for needle in ("AutomationSecurity = 3", "AddToRecentFiles", "Quit(0)", "Documents.Count"):
        assert needle in WORD_SCRIPT
    seen = []

    def fake_run(args, **kw):
        seen.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="1", stderr="")

    monkeypatch.setattr("jobme.applydocs.pages.sys.platform", "win32")
    monkeypatch.setattr("subprocess.run", fake_run)
    word_page_counter(b"x")
    doc_path, pid_path = seen[0][-2], seen[0][-1]
    assert doc_path not in WORD_SCRIPT and pid_path not in WORD_SCRIPT


def test_locked_temp_file_does_not_raise(monkeypatch):
    import tempfile
    used = {}
    real = tempfile.TemporaryDirectory

    def spy(*a, **k):
        used.update(k)
        return real(*a, **k)

    monkeypatch.setattr("jobme.applydocs.pages.sys.platform", "win32")
    monkeypatch.setattr("tempfile.TemporaryDirectory", spy)
    monkeypatch.setattr("subprocess.run", lambda a, **k: subprocess.CompletedProcess(a, 0, stdout="2", stderr=""))
    assert word_page_counter(b"x") == 2
    assert used.get("ignore_cleanup_errors") is True


def _failing_run(pid_text, stdout, code, calls):
    def fake_run(args, **kw):
        calls.append(args)
        if args[0] == "powershell.exe":
            if pid_text is not None:
                with open(_pid_file_of(args), "w") as f:
                    f.write(pid_text)
            return subprocess.CompletedProcess(args, code, stdout=stdout, stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
    return fake_run


def test_non_zero_exit_kills_the_recorded_word_pid(monkeypatch):
    calls = []
    monkeypatch.setattr("jobme.applydocs.pages.sys.platform", "win32")
    monkeypatch.setattr("subprocess.run", _failing_run("4321\r\n", "", 1, calls))
    assert word_page_counter(make_resume_docx()) is None
    assert [c for c in calls if c[0] == "taskkill"] == [["taskkill", "/PID", "4321", "/F"]]


def test_non_zero_exit_without_pid_file_or_with_bad_pid_kills_nothing(monkeypatch):
    monkeypatch.setattr("jobme.applydocs.pages.sys.platform", "win32")
    for text in (None, "1234; calc", "-5"):
        calls = []
        monkeypatch.setattr("subprocess.run", _failing_run(text, "", 1, calls))
        assert word_page_counter(make_resume_docx()) is None
        assert not [c for c in calls if c[0] == "taskkill"]


def test_clean_exit_with_bad_output_kills_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr("jobme.applydocs.pages.sys.platform", "win32")
    monkeypatch.setattr("subprocess.run", _failing_run("4321", "oops", 0, calls))
    assert word_page_counter(make_resume_docx()) is None
    assert not [c for c in calls if c[0] == "taskkill"]


def test_word_calls_hide_the_console_window(monkeypatch):
    from jobme.applydocs import pages

    calls = []
    monkeypatch.setattr("jobme.applydocs.pages.sys.platform", "win32")

    def fake_run(args, **kw):
        calls.append((args[0], kw))
        if args[0] == "powershell.exe":
            with open(_pid_file_of(args), "w") as f:
                f.write("4321")
            raise subprocess.TimeoutExpired("powershell", 90)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    assert word_page_counter(make_resume_docx()) is None
    assert [name for name, _ in calls] == ["powershell.exe", "taskkill"]
    assert all(kw["creationflags"] == pages.NO_WINDOW for _, kw in calls)
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        assert pages.NO_WINDOW == subprocess.CREATE_NO_WINDOW
