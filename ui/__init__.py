"""ui — the window, split by what each part owns.

WHY THE PACKAGE REPLACES ui.py
    `ui.py` was one 7,504-line module, and the size was the symptom: the palette
    was defined at the top and rebound by accent code a hundred lines below it,
    the metric sampler ran a thread in the same file as the widgets that read it,
    and NOTHING could be imported for a test without a display.

    There is no way to keep both a `ui.py` and a `ui/` package: Python resolves
    the directory first, so the file would be shadowed and its imports would
    fail — which is exactly what CI reported the first time this was attempted
    (`No module named 'ui.theme'; 'ui' is not a package`). So the file moved,
    whole, to `ui/window.py`, and this package re-exports it.

WHAT IS WHERE, AND WHAT THAT MEANS FOR YOU
    ui/theme.py    the palette (`C`) and the accent code — the only writer
    ui/metrics.py  the sampler thread: CPU, memory, network, GPU, temperature
    ui/window.py   the widgets and the window (still large; that is the next job)

    `ui.C`, `ui.qcol`, `ui.MainWindow`, `ui.JarvisUI`, `ui._metrics` all keep
    working: they are re-exported here, because plugins and main.py written
    against the old module must not care that it became a package.

IMPORTING THIS NEEDS QT. That has not changed. What changed is that anything
that only needs to know ABOUT the window — its structure, its rules, which file
owns what — no longer has to import it: tests/test_ui_split.py reads the AST.
"""
from ui.theme import (          # noqa: F401 — the public face of the package
    C,
    DEFAULT_UI_COLOR,
    apply_ui_accent,
    current_palette,
    qcol,
    retheme_all_widgets,
)
# THE FOUNDATIONS FIRST, AND BY NAME. `ui/metrics.py` imports no Qt, so if this
# module is broken the package says so AT THIS LINE — "cannot import name
# _metrics from ui.metrics" — instead of failing later inside the window with a
# message about something else. (It did: the sampler singleton was cut when the
# class moved, and the only thing that noticed was CI, on three runners.)
from ui.metrics import (        # noqa: F401 — the sampler the window reads
    _SysMetrics,
    _metrics,
    _nvml_gpu_windows,
)
from ui.window import *          # noqa: F401,F403 — the whole window, unchanged
