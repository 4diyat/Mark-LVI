"""Board 22 adapter — run a reviewed install plan through the real installer.

`core.install_plan.InstallPlan` is the policy: it decides which packages a
config needs and which are missing, and enforces the review gate. This module
is the I/O edge that turns an *approved* plan into real `pip` calls through
`core.installer`, which already owns the package tables and the subprocess.

WHY THE SPLIT. The policy is pure and fully tested with a fake install port.
The only logic worth unit-testing here is the thin mapping from the policy's
`Package` to the installer's `(module, pip_name)` call — and that is exactly
what `run_install_plan` does. The real pip execution is `core.installer`'s
job, not this module's.
"""
from __future__ import annotations

from typing import Callable

from core.install_plan import InstallPlan, PackageResult


def run_install_plan(
    plan: InstallPlan,
    log: Callable[[str], None] | None = None,
) -> list[PackageResult]:
    """Install a *reviewed* plan through `core.installer._pip`.

    For each missing package, call the installer's `_pip` with the pip name and
    the log callback. Returns one `PackageResult` per package in the plan (the
    missing ones installed, the present ones reported as already present).

    The policy's `apply_plan` owns the review gate and the result assembly;
    this function is the transport it calls. If the plan is unreviewed, the
    policy refuses before this is ever reached.
    """
    from core.install_plan import apply_plan
    from core.installer import _available, _pip

    def _install(package, cb):
        # Re-check availability: the policy checked at plan time, but a package
        # may have been installed since. The installer's _pip is the transport.
        if _available(package.module):
            return True
        return _pip(package.package, cb)

    return apply_plan(plan, _install, log=log)


__all__ = ["run_install_plan"]
