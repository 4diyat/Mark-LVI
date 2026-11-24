"""Board 22 — installer planning, as a pure policy.

Board 22 is the first-run screen where the owner picks a presence mode and,
the design says, the installer installs the dependencies that mode needs.
`core/installer.py` already knows how to run pip, but its logic is a single
block that mixes the *decision* (which packages a config needs, which are
missing, in what order) with the *transport* (subprocess, pip). The decision
deserves to be pure and testable on its own — the same split as routines,
form filling and phone pairing.

WHAT THIS MODULE IS. A policy module that, given a config (stt engine, tts
engine, platform) and an injectable "is this module available" predicate,
produces an :class:`InstallPlan`: the ordered list of packages that would be
installed, what is already present, and the plan's review state. It never
runs pip, never imports a missing module, and never touches the network — the
availability check is a predicate the caller supplies, so tests drive it with
a fake and the real adapter (`actions/installer.py`) supplies
`core.installer._available`.

THE PACKAGE LISTS ARE SHARED WITH THE INSTALLER, NOT COPIED. The authoritative
mapping of config → packages lives in `core/installer.py`; this module imports
those tables so a package added to the installer is automatically part of the
plan. The policy owns the *decision* (what's missing, order, review gate,
per-package result); the installer owns the *tables* and the *transport*.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.installer import _CORE, _STT, _TTS, _WINDOWS

# The version pins the installer applies on Windows under Python < 3.13, so
# the plan and the install agree. Keyed by the pip name.
_WINDOWS_PIN = {"numpy": "numpy>=1.24,<2", "opencv-python": "opencv-python>=4.8,<4.12"}


@dataclass(frozen=True)
class Package:
    """One dependency: the module to import, and the pip package to install."""

    module: str
    package: str


@dataclass(frozen=True)
class PackageResult:
    """Outcome for one package once a reviewed plan has been installed."""

    package: str
    ok: bool
    detail: str


@dataclass
class InstallPlan:
    """The packages an install would touch, and whether it was reviewed.

    Like `FormFillPlan`, the plan is *inert* until reviewed: an unreviewed
    plan reports that nothing has been installed, no matter what the adapter
    does. `packages` holds every package the config needs (present and
    missing alike) so the review screen can show the whole picture.
    """

    packages: tuple[Package, ...]
    missing: tuple[Package, ...]
    reviewed: bool = False

    @classmethod
    def build(cls, config: dict, is_available: Callable[[str], bool],
              platform_name: str = "") -> "InstallPlan":
        """Compute the packages a config needs and which are missing.

        `config` carries `stt_engine` and `tts_engine`; `platform_name` selects
        the Windows-only extras (the installer keys off `platform.system()`).
        `is_available` is the injected availability predicate. The result is
        the full package list plus the subset that is missing, in install
        order (core first, then engine, then platform extras, deduplicated by
        pip name with first-seen order kept).
        """
        needed: list[Package] = [
            Package(m, _WINDOWS_PIN.get(p, p) if platform_name == "Windows" else p)
            for m, p in _CORE
        ]
        stt = str(config.get("stt_engine", "whisper")).lower()
        tts = str(config.get("tts_engine", "edgetts")).lower()
        needed += [Package(m, p) for m, p in _STT.get(stt, [])]
        needed += [Package(m, p) for m, p in _TTS.get(tts, [])]
        if platform_name == "Windows":
            needed += [Package(m, p) for m, p in _WINDOWS]

        seen: set[str] = set()
        unique: list[Package] = []
        for pkg in needed:
            if pkg.package not in seen:
                seen.add(pkg.package)
                unique.append(pkg)

        missing = tuple(p for p in unique if not is_available(p.module))
        return cls(packages=tuple(unique), missing=missing)

    @property
    def needs_install(self) -> bool:
        """True when at least one package is missing."""
        return bool(self.missing)

    @property
    def installed(self) -> bool:
        """A plan is installed only when reviewed *and* the adapter ran."""
        return self.reviewed and getattr(self, "_installed", False)

    def review(self) -> "InstallPlan":
        """Mark the plan reviewed, returning it for chaining."""
        self.reviewed = True
        return self

    def summary_lines(self) -> list[str]:
        """Human-readable lines for the board's review screen."""
        lines = []
        for pkg in self.packages:
            mark = "✓" if pkg.package in self._missing_names else "—"
            lines.append(f"{mark} {pkg.package}")
        if not self.reviewed:
            lines.append("belum ditinjau — belum diinstal")
        return lines

    @property
    def _missing_names(self) -> set[str]:
        """The pip names of the packages this plan would install."""
        return {p.package for p in self.missing}


def apply_plan(
    plan: InstallPlan,
    install: Callable[[Package, Callable | None], bool],
    log: Callable[[str], None] | None = None,
) -> list[PackageResult]:
    """Install a *reviewed* plan through an `install` port, per package.

    `install(package, log)` is the transport to the real installer: it takes a
    :class:`Package` and a log callback and returns whether it succeeded.
    This function enforces the review gate — an unreviewed plan is refused
    outright — and records results for every missing package. Packages that
    were already present are reported as ok without being installed.
    """
    if not plan.reviewed:
        raise InstallError("Plan not reviewed — refusing to install an unreviewed plan.")
    results: list[PackageResult] = []
    for pkg in plan.missing:
        try:
            ok = bool(install(pkg, log))
        except Exception as exc:                    # noqa: BLE001
            results.append(PackageResult(pkg.package, False, str(exc)))
            continue
        results.append(PackageResult(pkg.package, ok, "ok" if ok else "failed"))
    for pkg in plan.packages:
        if pkg.package not in plan._missing_names:
            results.append(PackageResult(pkg.package, True, "already present"))
    if results:
        plan._installed = True  # type: ignore[attr-defined]
    return results


class InstallError(ValueError):
    """Raised when an install plan cannot be built or applied."""


__all__ = [
    "InstallError",
    "InstallPlan",
    "Package",
    "PackageResult",
    "apply_plan",
]
