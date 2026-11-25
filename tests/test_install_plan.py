"""Tests for the board 22 install-planning policy (no pip or network).

`core.install_plan.InstallPlan` is a pure policy: given a config and an
injected availability predicate, it computes which packages an install would
touch, which are missing, and enforces the review gate before anything is
installed. Every rule is tested with a fake `is_available` predicate.
"""
import pytest

from core.install_plan import (
    InstallError,
    InstallPlan,
    Package,
    apply_plan,
)


def _plan(config=None, available=None, platform_name=""):
    config = config or {}
    pred = available or (lambda module: False)
    return InstallPlan.build(config, pred, platform_name=platform_name)


def _all_available(available_names):
    names = set(available_names)
    return lambda module: module in names or module.split(".")[0] in names


# -- building the plan ----------------------------------------------------
def test_build_returns_the_core_packages_when_nothing_is_available():
    plan = _plan()
    assert plan.packages, "a config always needs the core packages"
    assert plan.needs_install is True
    assert len(plan.missing) == len(plan.packages)


def test_build_marks_present_packages_as_not_missing():
    plan = _plan(available=_all_available({"numpy", "requests"}))
    present = {p.package for p in plan.packages if p.module in ("numpy", "requests")}
    assert present <= {p.package for p in plan.packages}
    # numpy and requests are available, so they are not in the missing set.
    missing_names = {p.package for p in plan.missing}
    assert "numpy" not in missing_names
    assert "requests" not in missing_names


def test_build_uses_the_stt_engine_from_config():
    whisper = _plan({"stt_engine": "whisper"})
    vosk = _plan({"stt_engine": "vosk"})
    whisper_pkgs = {p.package for p in whisper.packages}
    vosk_pkgs = {p.package for p in vosk.packages}
    assert "faster-whisper" in whisper_pkgs
    assert "vosk" in vosk_pkgs
    assert "faster-whisper" not in vosk_pkgs


def test_build_uses_the_tts_engine_from_config():
    edge = _plan({"tts_engine": "edgetts"})
    kokoro = _plan({"tts_engine": "kokoro"})
    assert "edge-tts" in {p.package for p in edge.packages}
    assert "kokoro>=0.9" in {p.package for p in kokoro.packages}


def test_build_adds_windows_extras_only_on_windows():
    win = _plan(platform_name="Windows")
    other = _plan(platform_name="Linux")
    win_pkgs = {p.package for p in win.packages}
    other_pkgs = {p.package for p in other.packages}
    assert "pywinauto" in win_pkgs
    assert "pywinauto" not in other_pkgs


def test_build_pins_numpy_and_opencv_on_windows():
    win = _plan(platform_name="Windows")
    names = {p.package for p in win.packages}
    assert "numpy>=1.24,<2" in names
    assert "opencv-python>=4.8,<4.12" in names


def test_build_deduplicates_by_pip_name_keeping_first_order():
    plan = _plan()
    packages = [p.package for p in plan.packages]
    assert len(packages) == len(set(packages)), "pip names are unique"


def test_needs_install_is_false_when_everything_is_present():
    plan = _plan(available=lambda module: True)
    assert plan.needs_install is False
    assert plan.missing == ()


# -- review gate ---------------------------------------------------------
def test_unreviewed_plan_refuses_to_install():
    plan = _plan()
    called = []
    with pytest.raises(InstallError):
        apply_plan(plan, lambda pkg, log: called.append(pkg) or True)
    assert called == [], "an unreviewed plan must not call the installer"


def test_reviewed_plan_installs_only_missing_packages():
    plan = _plan(available=_all_available({"numpy"})).review()
    installed = []
    results = apply_plan(plan, lambda pkg, log: installed.append(pkg.package) or True)
    missing_names = {p.package for p in plan.missing}
    assert set(installed) == missing_names
    assert all(r.ok for r in results if r.package in missing_names)
    assert plan.installed is True


def test_review_returns_the_plan_for_chaining():
    plan = _plan()
    assert plan.review() is plan
    assert plan.reviewed is True


def test_installed_is_false_until_the_adapter_runs():
    plan = _plan().review()
    assert plan.installed is False
    apply_plan(plan, lambda pkg, log: True)
    assert plan.installed is True


# -- results & summaries ------------------------------------------------
def test_present_packages_are_reported_without_installing():
    plan = _plan(available=_all_available({"numpy"})).review()
    installed = []
    results = apply_plan(plan, lambda pkg, log: installed.append(pkg.package) or True)
    assert "numpy" not in installed
    numpy_result = next(r for r in results if r.package == "numpy")
    assert numpy_result.ok is True
    assert "already present" in numpy_result.detail


def test_a_failing_package_is_reported_and_does_not_stop_the_rest():
    plan = _plan().review()

    def install(pkg, log):
        return pkg.package != "psutil"

    results = apply_plan(plan, install)
    psutil = next(r for r in results if r.package == "psutil")
    assert psutil.ok is False
    assert psutil.detail == "failed"


def test_summary_lines_mark_missing_with_a_check():
    plan = _plan(available=_all_available({"numpy"}))
    lines = plan.summary_lines()
    assert any(line.startswith("✓ ") for line in lines)
    assert any("belum ditinjau" in line for line in lines)


def test_summary_lines_drop_the_unreviewed_note_after_review():
    plan = _plan().review()
    assert not any("belum ditinjau" in line for line in plan.summary_lines())


def test_package_is_a_frozen_pair():
    pkg = Package("numpy", "numpy")
    assert pkg.module == "numpy"
    assert pkg.package == "numpy"
