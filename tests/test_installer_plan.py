"""Tests for the board 22 install adapter (pip mocked, no real install).

`actions.installer_plan.run_install_plan` is the I/O edge: it maps the policy's
`Package` to `core.installer._pip` calls. The real pip execution is mocked so
the test proves the mapping and the review gate without touching the network.
"""
import pytest

from actions.installer_plan import run_install_plan
from core.install_plan import InstallError, InstallPlan


def _plan(available_names=None):
    names = set(available_names or ())
    pred = lambda module: module in names
    return InstallPlan.build({}, pred, platform_name="").review()


def test_run_install_plan_installs_missing_packages_through_pip(monkeypatch):
    called = []

    def fake_pip(package, log=None):
        called.append(package)
        return True

    monkeypatch.setattr("core.installer._pip", fake_pip)
    monkeypatch.setattr("core.installer._available", lambda module: False)

    plan = _plan()
    results = run_install_plan(plan)
    assert called, "the adapter must call _pip for each missing package"
    assert all(r.ok for r in results)
    assert plan.installed is True


def test_run_install_plan_skips_packages_that_became_available(monkeypatch):
    """A package installed since planning is not re-piped."""
    called = []

    def fake_pip(package, log=None):
        called.append(package)
        return True

    # At plan time numpy was missing; by install time it is present.
    monkeypatch.setattr("core.installer._available", lambda module: module == "numpy")
    monkeypatch.setattr("core.installer._pip", fake_pip)

    plan = _plan()
    results = run_install_plan(plan)
    piped = [p for p in called]
    assert "numpy" not in piped
    numpy_result = next(r for r in results if r.package == "numpy")
    assert numpy_result.ok is True


def test_run_install_plan_refuses_an_unreviewed_plan(monkeypatch):
    plan = InstallPlan.build({}, lambda module: False, platform_name="")
    assert plan.reviewed is False
    with pytest.raises(InstallError):
        run_install_plan(plan)


def test_run_install_plan_reports_a_failing_pip(monkeypatch):
    def fake_pip(package, log=None):
        return package != "psutil"

    monkeypatch.setattr("core.installer._pip", fake_pip)
    monkeypatch.setattr("core.installer._available", lambda module: False)

    plan = _plan()
    results = run_install_plan(plan)
    psutil = next(r for r in results if r.package == "psutil")
    assert psutil.ok is False
