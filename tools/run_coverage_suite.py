"""Run the coverage suite with a deadline and actionable CI diagnostics.

A hung test previously left the Windows job running for hours with no completed
logs. A temporary transcript keeps the most recent test name available even
when the child must be stopped. This does not replace the coverage ratchet.

WHY IT ALSO REPORTS FAILURES
    This step runs the suite a SECOND time, under the tracer, and only its exit
    status decides the job. So a test that fails here while passing in the plain
    suite turns the job red with nothing to read: the step prints a 30,000-line
    transcript to a log that this repository's token frequently cannot fetch (it
    returns EOF), and the UI says only "Process completed with exit code 1".

    That is the same problem `tools/annotate_junit.py` was written for, one step
    later: the plain suite writes junit XML and gets annotations; this run wrote
    nothing. It now names the failing tests in an `::error` line, so the answer
    is on the pull request instead of in a log nobody can download.

    The tracer changes timing and line-tracing behaviour, so a difference here
    is real signal about a timing-dependent test, not noise to be suppressed.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT_SECONDS = 300

# pytest's short summary: "FAILED tests/x.py::test_y - AssertionError: ..."
_FAILED = re.compile(r"(?m)^FAILED\s+(\S+)(?:\s+-\s+(.*))?$")
_ERRORED = re.compile(r"(?m)^ERROR\s+(\S+)(?:\s+-\s+(.*))?$")


def last_test(transcript: str) -> str:
    """Return a pytest node id, not arbitrary test output, for the annotation."""
    matches = re.findall(r"(?m)^((?:tests[/\\][^\s:]+(?:::([^\s]+))+))", transcript)
    return matches[-1][0][:400] if matches else "unknown (before first test)"


def failures(transcript: str) -> list[tuple[str, str]]:
    """The failing/erroring node ids and their first line of reason."""
    found = []
    for pattern in (_FAILED, _ERRORED):
        for node_id, reason in pattern.findall(transcript):
            found.append((node_id.strip(), (reason or "").strip()))
    return found


def _escape(text: str) -> str:
    """GitHub annotation escapes, in this order."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def run_subprocess(timeout: int = TIMEOUT_SECONDS) -> tuple[int, str, bool]:
    """Run the suite under the tracer.

    Returns (exit status, transcript, timed_out). The third element is returned
    rather than inferred from the transcript: a killed process and a failed
    process both read as status 1, and guessing which happened from the text is
    how the wrong annotation gets printed.

    Split out from `run` so the REPORTING can be tested without running the
    whole suite a second time: the reporter is the part that was wrong, and it
    cannot be read in a CI log this repository often cannot download.
    """
    command = [sys.executable, "-m", "coverage", "run", "--source=core,memory,dashboard",
               "-m", "pytest", "-o", "addopts=", "-vv"]
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "pytest.log"
        with path.open("w+b") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env)
            timed_out = False
            try:
                status = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                process.wait()
                status = 1
            log.flush()
            log.seek(0)
            return status, log.read().decode("utf-8", errors="replace"), timed_out


def run(timeout: int = TIMEOUT_SECONDS) -> int:
    status, transcript, timed_out = run_subprocess(timeout)
    # Keep CI logs manageable while retaining the end of a failure trace.
    print(transcript[-30000:], flush=True)
    if timed_out:
        name = last_test(transcript).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        tail = transcript[-2000:].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=Coverage suite timed out::Coverage suite exceeded {timeout}s; "
              f"last started test: {name}%0A{tail}", flush=True)
    elif status != 0:
        problems = failures(transcript)
        if problems:
            for node_id, reason in problems[:10]:
                print(f"::error title=Failed under the coverage tracer::{_escape(node_id)} "
                      f"-- {_escape(reason)[:200]}", flush=True)
            if len(problems) > 10:
                print(f"::error title=Failed under the coverage tracer::"
                      f"and {len(problems) - 10} more; see the transcript above",
                      flush=True)
        else:
            # No summary line to parse: name the tail so the annotation is still
            # more useful than "exit code 1".
            print("::error title=Coverage suite failed::no FAILED/ERROR summary "
                  f"could be parsed; last started test: {last_test(transcript)}%0A"
                  f"{_escape(transcript[-1200:])}", flush=True)
    return status


if __name__ == "__main__":
    sys.exit(run())
