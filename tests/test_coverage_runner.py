"""The coverage runner must identify a hung test without trusting its output."""
import subprocess

from tools import run_coverage_suite as runner


def test_last_test_uses_pytest_node_id_only():
    transcript = 'tests/test_first.py::test_ok PASSED\ntests/test_second.py::test_hung[param] '
    assert runner.last_test(transcript) == 'tests/test_second.py::test_hung[param]'
    assert runner.last_test('nothing collected') == 'unknown (before first test)'


def test_timeout_reports_last_test_and_fails(monkeypatch, capsys):
    class Process:
        def __init__(self, command, stdout, **kwargs):
            assert command[-4:] == ['pytest', '-o', 'addopts=', '-vv']
            self.stdout = stdout
            self.stdout.write(b'tests/test_example.py::test_slow ')
            self.killed = False
        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired('pytest', timeout)
            return -1
        def kill(self):
            self.killed = True
    monkeypatch.setattr(runner.subprocess, 'Popen', Process)
    assert runner.run(timeout=1) == 1
    assert 'last started test: tests/test_example.py::test_slow' in capsys.readouterr().out


# ── naming the failure, not just reporting one ──────────────────────────────
#
# The coverage step re-runs the suite under the tracer and only its exit status
# decides the job. A test that fails here — and nowhere else — used to turn the
# job red with an unreadable log: the plain suite gets junit annotations and
# this run wrote none. These cover the parser that closes that gap.

def test_failures_reads_the_short_summary():
    transcript = (
        "FAILED tests/test_x.py::test_a - AssertionError: 1 != 2\n"
        "FAILED tests/test_x.py::test_b - KeyError: 'k'\n"
        "ERROR tests/test_y.py::test_c\n"
        "123 passed, 2 failed, 1 error\n"
    )
    assert runner.failures(transcript) == [
        ("tests/test_x.py::test_a", "AssertionError: 1 != 2"),
        ("tests/test_x.py::test_b", "KeyError: 'k'"),
        ("tests/test_y.py::test_c", ""),
    ]


def test_failures_is_empty_on_a_clean_run():
    assert runner.failures("1283 passed, 4 skipped in 25.42s\n") == []


def test_a_parsed_failure_is_reported_as_an_annotation(monkeypatch, capsys):
    transcript = "FAILED tests/test_x.py::test_a - AssertionError: nope\n1 failed\n"
    monkeypatch.setattr(runner, "run_subprocess", lambda timeout: (1, transcript, False))
    runner.run(timeout=1)
    out = capsys.readouterr().out
    assert "::error title=Failed under the coverage tracer::" in out
    assert "tests/test_x.py::test_a" in out


def test_a_crash_without_a_summary_still_names_the_last_test(monkeypatch, capsys):
    """A crash that never reaches the summary must not report "exit code 1"."""
    transcript = "tests/test_z.py::test_d\nFatal Python error: Segmentation fault\n"
    monkeypatch.setattr(runner, "run_subprocess", lambda timeout: (1, transcript, False))
    runner.run(timeout=1)
    out = capsys.readouterr().out
    assert "::error" in out and "test_d" in out


def test_a_timeout_is_reported_as_a_timeout_not_as_a_failure(monkeypatch, capsys):
    """Killed and failed both read as status 1; the caller is told which it was."""
    transcript = "tests/test_slow.py::test_forever \n"
    monkeypatch.setattr(runner, "run_subprocess", lambda timeout: (1, transcript, True))
    runner.run(timeout=1)
    out = capsys.readouterr().out
    assert "timed out" in out
    assert "Failed under the coverage tracer" not in out


def test_a_clean_run_prints_no_error_annotation(monkeypatch, capsys):
    monkeypatch.setattr(runner, "run_subprocess",
                        lambda timeout: (0, "1283 passed in 25.42s\n", False))
    assert runner.run(timeout=1) == 0
    assert "::error" not in capsys.readouterr().out
