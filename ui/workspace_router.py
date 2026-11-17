"""Dispatch interactive plugin windows on the Qt main thread."""


def open_workspace(window, job):
    if job.get("kind") == "ssh_manager":
        from ui.ssh_manager import open_ssh_manager
        open_ssh_manager(window, job)
    elif job.get("kind") == "workspace_browser":
        try:
            from ui.workspace_browser import open_browser
        except ImportError:
            from core.i18n import label
            window.write_log(label("browser.unavailable"))
            return
        open_browser(window, job)
    elif job.get("kind") == "image_editor":
        from ui.image_editor import open_editor
        try:
            allowed = any(r.get("name") == "image_editor" and r.get("valid") and r.get("enabled")
                          for r in window.get_plugins())
        except Exception:
            allowed = False
        if allowed:
            open_editor(window, job)
    elif job.get("kind") == "mt5_trade":
        from ui.mt5_trade import open_trade
        open_trade(window, job)
    elif job.get("kind") == "trading_terminal":
        from ui.trading_terminal import open_terminal
        open_terminal(window, job)
    elif job.get("kind") == "creative_workspace":
        from ui.creative import open_workspace as open_creative
        open_creative(window, job)
