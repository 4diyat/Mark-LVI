"""Run the coverage suite with a deadline and actionable CI diagnostics.

A hung test previously left the Windows job running for hours with no completed
logs. A temporary transcript keeps the most recent test name available even
when the child must be stopped. This does not replace the coverage ratchet.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT_SECONDS = 300


def last_test(transcript: str) -> str:
    """Return a pytest node id, not arbitrary test output, for the annotation."""
    matches = re.findall(r"(?m)^((?:tests[/\\][^\s:]+(?:::([^\s]+))+))", transcript)
    return matches[-1][0][:400] if matches else "unknown (before first test)"


def run(timeout: int = TIMEOUT_SECONDS) -> int:
    command = [sys.executable, "-m", "coverage", "run", "--source=core,memory,dashboard",
               "-m", "pytest", "-v"]
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
            transcript = log.read().decode("utf-8", errors="replace")
        # Keep CI logs manageable while retaining the end of a failure trace.
        print(transcript[-30000:], flush=True)
        if timed_out:
            name = last_test(transcript).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::error title=Coverage suite timed out::Coverage suite exceeded {timeout}s; "
                  f"last started test: {name}", flush=True)
        return status


if __name__ == "__main__":
    sys.exit(run())
