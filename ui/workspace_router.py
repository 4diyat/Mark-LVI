"""Dispatch interactive plugin windows on the Qt main thread."""


def open_workspace(window, job):
    if job.get("kind") == "trading_terminal":
        from ui.trading_terminal import open_terminal
        open_terminal(window, job)
    elif job.get("kind") == "creative_workspace":
        from ui.creative import open_workspace as open_creative
        open_creative(window, job)
