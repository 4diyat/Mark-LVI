"""Diagnose a hang: prints every step of startup, and dumps a stack on a stall.

WHY THIS EXISTS
    "It still hangs" is not enough to fix a hang from. The application can hang
    in at least four different places, and each one has a different fix:

      * before QApplication exists      -> an import or a driver
      * during start_interface          -> a surface blocking the Qt thread
      * after start_interface, in exec() -> the event loop IS running; the hang
                                           is a surface that never yields
      * in the runner thread            -> the Qt thread is fine and the user is
                                           waiting on audio/auth instead

    This script does not guess between them. Every step prints a timestamped
    line, and a watchdog thread dumps the stack of EVERY thread if the gap
    between two steps exceeds --stall seconds. Run it, wait for the hang, then
    paste the output.

HOW TO RUN (Windows)
    python tools_diag.py
    python tools_diag.py --stall 15
    python tools_diag.py --stall 10 > diag.txt 2>&1

WHAT IT DOES NOT DO
    It does not change the application: every step is the real function, called
    in the real order. It only wraps them with a print and a timer.
"""
from __future__ import annotations

import argparse
import faulthandler
import sys
import threading
import time
import traceback


def main() -> int:
    parser = argparse.ArgumentParser(description="Find where JARVIS hangs.")
    parser.add_argument("--stall", type=float, default=20.0,
                        help="seconds without progress before a stack is dumped")
    parser.add_argument("--exit-after", type=float, default=0.0,
                        help="quit by itself after N seconds (0 = never)")
    parser.add_argument("--heartbeat", action="store_true",
                        help="print a line every second from the Qt thread")
    args = parser.parse_args()

    start = time.time()
    lock = threading.Lock()
    last = {"at": start, "step": "starting"}
    step_no = {"n": 0}

    def stamp(name: str) -> None:
        now = time.time()
        with lock:
            gap = now - last["at"]
            last["at"], last["step"] = now, name
            step_no["n"] += 1
            print(f"[{now - start:7.2f}s] {step_no['n']:02d} {name}"
                  + (f"   (+{gap:.2f}s)" if gap > 2 else ""), flush=True)

    def watchdog() -> None:
        while True:
            time.sleep(0.25)
            with lock:
                quiet = time.time() - last["at"]
                where = last["step"]
            if quiet >= args.stall:
                print(f"\n!!! NO PROGRESS FOR {quiet:.0f}s, last step: {where}\n",
                      flush=True)
                faulthandler.dump_traceback(file=sys.stdout, all_threads=True)
                print("!!! end of stacks — paste everything above\n", flush=True)
                with lock:
                    last["at"] = time.time()      # do not spam

    threading.Thread(target=watchdog, daemon=True, name="diag-watchdog").start()

    stamp("python imports done")
    try:
        import main as app

        stamp("main.py imported (module level: config, logbook, sdk)")
    except BaseException as exc:                  # noqa: BLE001
        stamp(f"main.py FAILED TO IMPORT: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 2

    stamp("building QApplication")
    try:
        options, qt_argv = app._parse_args([])
        shell_app = app._make_application(qt_argv)
        stamp(f"QApplication ready (platform={sys.platform})")
    except BaseException as exc:                  # noqa: BLE001
        stamp(f"QApplication FAILED: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 3

    from ui.shell import AmbientShell

    stamp("building AmbientShell")
    ui = AmbientShell(face_path=app._face_path(), app=shell_app)
    ui._launch = options
    ui._program_path = str(__import__("pathlib").Path(app.__file__).resolve())
    stamp("AmbientShell ready")

    # EVERY SURFACE, ONE AT A TIME, WITH ITS OWN TIMER. start_interface() calls
    # them in this order; doing it here names the one that blocks.
    for label, fn_name, module in (
        ("tray", "start_tray", "ui.lifecycle"),
        ("face bubble", "start_bubble", "ui.lifecycle"),
        ("orb", "start_orb", "ui.ambient_shell"),
        ("command bar", "start_command_bar", "ui.ambient_shell"),
        ("voice overlay", "start_voice_overlay", "ui.voice_wiring"),
        ("summon hotkey", "start_summon_hotkey", "ui.lifecycle"),
    ):
        mod = __import__(module, fromlist=[fn_name])
        fn = getattr(mod, fn_name)
        stamp(f"{label}: calling {fn_name}")
        try:
            result = fn(ui)
            stamp(f"{label}: returned {result!r}")
        except BaseException as exc:              # noqa: BLE001
            stamp(f"{label}: RAISED {type(exc).__name__}: {exc}")

    stamp("all surfaces attempted — main-thread work done")
    stamp("entering the Qt event loop (app.exec)")

    if args.exit_after:
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(int(args.exit_after * 1000), shell_app.quit)
        stamp(f"will quit by itself in {args.exit_after:.0f}s")

    # THE HEARTBEAT IS THE WHOLE POINT OF THE EVENT-LOOP PHASE. A Qt timer only
    # fires when the loop is servicing events, so a heartbeat that stops is a
    # loop that is blocked — prints from other threads keep coming, which is
    # what makes "hang" and "dead" different diagnoses.
    from PyQt6.QtCore import QTimer

    if args.heartbeat:
        beat = QTimer()
        beat.setInterval(1000)
        beat.timeout.connect(lambda: stamp("Qt thread alive"))
        beat.start()

    # And the REAL startup path, so this run is comparable to the app's own.
    threading.Thread(target=lambda: _runner(app, ui, stamp), daemon=True).start()
    shell_app.exec()
    stamp("event loop returned")
    return 0


def _runner(app, ui, stamp) -> None:
    stamp("runner thread: waiting for the API key")
    ui.wait_for_api_key()
    stamp("runner thread: key present, building JarvisLive")
    import asyncio

    try:
        jarvis = app.JarvisLive(ui)
        stamp("runner thread: JarvisLive built, starting asyncio loop")
        asyncio.run(jarvis.run())
    except BaseException as exc:                  # noqa: BLE001
        stamp(f"runner thread RAISED {type(exc).__name__}: {exc}")
        traceback.print_exc()


if __name__ == "__main__":
    raise SystemExit(main())
