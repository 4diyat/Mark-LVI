"""The workflow is code, and it runs on three shells. This reads it as YAML.

WHY
    .github/workflows/ci.yml broke three times in a row, and never because a
    test failed:

      * a `set +e` block and `$?` in a step Windows runs with PowerShell;
      * a `python - <<'REPORT'` heredoc, which is bash syntax — on Windows it
        failed on line one and hid the four real failures it was written to
        explain;
      * `... | tail -5` in the same situation.

    Each one cost a push and a full CI cycle to discover, on a check whose
    purpose was to make failures cheaper to diagnose. All three are visible
    without running anything: the body of a step either contains shell syntax
    that only bash understands, or it does not.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

# Things that mean "this body is a bash script". Deliberately narrow: a false
# positive costs one line of YAML (`shell: bash`), a false negative costs a CI
# cycle on whichever runner is unlucky.
BASH_ONLY = {
    "$?": "the exit status of the last command",
    "|| true": "'do not fail here' — PowerShell has no ||",
    "&& ": "'and' — PowerShell has no &&",
    "| tail": "a pipe to a coreutility",
    "| head": "a pipe to a coreutility",
    "<<": "a heredoc",
    "set -e": "bash's errexit",
    "set +e": "bash's errexit toggle",
    "\\\n": "a line continuation",
}


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def steps(workflow):
    for job_name, job in workflow["jobs"].items():
        for step in job["steps"]:
            yield job_name, step


def test_every_shell_only_body_declares_its_shell(workflow):
    """`run:` defaults to bash on Linux/macOS and PowerShell on Windows. A body
    written in one and run by the other fails for a reason nobody can see."""
    offenders = []
    for job_name, step in steps(workflow):
        body = step.get("run") or ""
        if not body or step.get("shell"):
            continue
        for marker, why in BASH_ONLY.items():
            if marker in body:
                offenders.append(
                    f"{job_name} / {step.get('name')!r}: uses {marker!r} ({why})")
    assert offenders == [], (
        "these steps use bash syntax without `shell: bash`, so they behave "
        "differently on Windows:\n  " + "\n  ".join(offenders))


def test_no_step_body_is_a_heredoc(workflow):
    """Heredocs are the one bash-ism that Windows cannot survive at all, and the
    reason tools/annotate_junit.py exists as a file."""
    heredocs = [f"{job} / {step.get('name')!r}"
                for job, step in steps(workflow)
                if "<<" in (step.get("run") or "")]
    assert heredocs == [], (
        "these steps build a script inside the workflow; put it in tools/ "
        "where it can also be tested:\n  " + "\n  ".join(heredocs))


def test_every_step_that_fails_the_job_does_so_on_purpose(workflow):
    """A step with `if: always()` that can exit non-zero is how a job reports a
    failure it already knows about. The two are allowed, but a bare `if:
    always()` step must not be able to fail by accident: this asserts the
    report/print steps either cannot fail or say so."""
    for job, step in steps(workflow):
        if step.get("if") != "always()":
            continue
        body = step.get("run") or ""
        # These steps are allowed to be plain (they only print or inspect), but
        # one that also *judges* the run is a step that can hide a result.
        if "--fail-under" in body:
            assert "|| true" in body or "set +e" in body or "shell" in step, (
                f"{job} / {step.get('name')!r} prints nothing if the suite "
                "before it failed; make it report first")


def test_the_test_job_installs_only_the_dev_requirements(workflow):
    """By design: the suite must not need Qt, torch or a GPU. A step that starts
    installing the app's requirements here turns a fast check into a slow one
    and hides a test that only passes with them."""
    job = workflow["jobs"]["test"]
    installs = [s for s in job["steps"]
                if "pip install" in (s.get("run") or "")
                or "requirements" in (s.get("run") or "")]
    for step in installs:
        body = step.get("run") or ""
        assert "requirements.txt" not in body.replace("requirements-dev.txt", ""), (
            f"{step.get('name')!r} installs the app's requirements into the "
            "test job")


def test_pytest_writes_the_junit_file_the_reporter_reads(workflow):
    """The reporter is useless if nothing produces its input, and the paths have
    to agree exactly — this is the wiring test for the pair."""
    job = workflow["jobs"]["test"]
    run_suite = next(s for s in job["steps"] if s.get("name") == "Run the suite")
    reporter = next(s for s in job["steps"]
                    if s.get("name") == "Report failures as annotations")
    assert "runner.temp" in run_suite["run"]
    assert "runner.temp" in reporter["run"]
    assert "junit.xml" in run_suite["run"] and "junit.xml" in reporter["run"]


def test_the_ambient_smoke_tool_runs_with_real_qt(workflow):
    """The window's smoke tools are gone; the replacement must actually run.

    Five scripts drove `ui.window` with real Qt offscreen and they all went with
    the window. What replaces them has to be wired the same way — through
    `run_qt_smoke.py`, on Linux, offscreen — or the surfaces that remain lose
    their only check against real Qt rather than the test stub.
    """
    job = workflow["jobs"]["install"]
    step = next(s for s in job["steps"]
                if s.get("name") == "Exercise the ambient surfaces with real Qt offscreen")
    assert step["env"]["QT_QPA_PLATFORM"] == "offscreen"
    assert "tools/run_qt_smoke.py tools/check_ambient_qt.py" in step["run"]
    assert (ROOT / "tools" / "check_ambient_qt.py").is_file()


def test_the_window_smoke_tools_are_not_still_wired():
    """A workflow step pointing at a deleted script fails on the NEXT run.

    Asserted both halves: the file is gone and the workflow no longer names it,
    because deleting only one of them is a red build nobody notices until the
    Linux job runs — which is the one job a local `pytest` cannot check.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    for name in ("check_desktop_qt.py", "capture_desktop_qt.py",
                 "check_browser_qt.py", "capture_browser_qt.py",
                 "check_ssh_qt.py", "check_security_qt.py"):
        assert not (ROOT / "tools" / name).is_file(), f"tools/{name} is back"
        assert f"tools/{name}" not in text, f"CI still runs tools/{name}"


def test_plugin_discovery_ci_step_matches_shipped_permissions(workflow, isolated_config, monkeypatch):
    """Execute CI's plugin assertions against isolated, default-off settings."""
    monkeypatch.chdir(ROOT)
    step = next(step for job, step in steps(workflow)
                if job == 'install' and step.get('name') == 'Load every plugin through the real loader')
    assert step['shell'] == 'python'
    exec(compile(step['run'], str(WORKFLOW), 'exec'), {})
