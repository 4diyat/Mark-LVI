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
