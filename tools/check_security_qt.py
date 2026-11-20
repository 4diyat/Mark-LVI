"""Exercise security controls with real Qt, offline and with temporary config.

The offscreen platform tests widget wiring, not visual quality, real TLS trust,
MetaTrader, or whether the application works with an actual display or camera.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox, QWidget  # noqa: E402

import memory.config_manager as config  # noqa: E402
from core import i18n, trade_gate  # noqa: E402
from ui.mt5_trade import OrderDialog  # noqa: E402
from ui.window import RemoteKeyOverlay  # noqa: E402


def main():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        config.CONFIG_DIR = Path(tmp)
        config.CONFIG_FILE = Path(tmp) / "api_keys.json"
        config._LAST_GOOD = {}
        # Avoid querying the machine firewall; no listener or network is used.
        import dashboard.server as server
        server.blocking_firewall_rules = lambda: []
        parent = QWidget()
        parent.resize(820, 580)
        parent.show()
        from memory import memory_manager
        from ui.hud_panels import MemoryOverlay
        memory_manager.MEMORY_PATH = Path(tmp) / "long_term.json"
        memory_manager.update_memory({"notes": {"example": "kept"}})
        for locale in ("en", "id"):
            i18n.set_locale(locale)
            memory_view = MemoryOverlay(parent)
            memory_view.show()
            with patch.object(memory_manager.os, 'replace', side_effect=OSError("blocked")):
                memory_view._forget("notes", "example")
            assert memory_manager.load_memory()["notes"]["example"]["value"] == "kept"
            assert any(label.text() == i18n.label("ui.memory.save_error")
                       for label in memory_view.findChildren(QLabel))
            memory_view.close()
            assert config.set_config_values(dashboard_https=False, sentinel="preserved")
            overlay = RemoteKeyOverlay("http://192.0.2.10:8000", "ABCDEFGH", parent=parent)
            overlay.setGeometry(0, 0, overlay._OW, overlay._OH)
            overlay.show()
            app.processEvents()
            assert overlay._https_status.text() == i18n.label("remote.http.warning")
            assert overlay._https_button.isVisible()
            QTest.mouseClick(overlay._https_button, Qt.MouseButton.LeftButton)
            app.processEvents()
            assert config.load_api_keys()["dashboard_https"] is True
            assert config.load_api_keys()["sentinel"] == "preserved"
            assert overlay._https_status.text() == i18n.label("remote.https.restart")
            assert overlay._manual_url.startswith("http://")
            assert not overlay._https_button.isVisible()
            overlay.close()

            trade_gate.resume()
            dialog = OrderDialog(parent, {})
            dialog.show()
            app.processEvents()
            dialog.mode.setCurrentIndex(1)
            QTest.mouseClick(dialog.stop_button, Qt.MouseButton.LeftButton)
            assert trade_gate.stopped() and dialog.mode.currentData() == "OFF"
            assert not dialog.review.isEnabled()
            assert dialog.gate_status.text() == i18n.label("trade.stopped")
            second = OrderDialog(parent, {})
            second.show()
            app.processEvents()
            assert not second.review.isEnabled()
            original_question = QMessageBox.question
            try:
                QMessageBox.question = lambda *_: QMessageBox.StandardButton.No
                QTest.mouseClick(second.resume_button, Qt.MouseButton.LeftButton)
                assert trade_gate.stopped()
                QMessageBox.question = lambda *_: QMessageBox.StandardButton.Yes
                QTest.mouseClick(second.resume_button, Qt.MouseButton.LeftButton)
                assert not trade_gate.stopped() and second.review.isEnabled()
                assert second.mode.currentData() == "OFF"
            finally:
                QMessageBox.question = original_question
                second.close()
                dialog.close()
                trade_gate.resume()
                app.processEvents()
        parent.close()
    print("Real Qt security controls passed in English and Indonesian (offscreen).")


if __name__ == "__main__":
    main()
