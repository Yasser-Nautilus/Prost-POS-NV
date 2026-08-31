import os
import sys
import logging
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QMessageBox
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineScript
from PyQt6.QtWebChannel import QWebChannel
from broast_pos.infrastructure.web_bridge.bridge import POSBridge

logger = logging.getLogger(__name__)


class WebShell(QMainWindow):
    """
    Main shell hosting the QWebEngineView for the React POS interface.
    Handles environment detection (dev server vs packaged bundle) and bridges Python logic.

    Key behaviour:
      - Injects qwebchannel.js at document creation so window.QWebChannel is always available.
      - Uses QWebEngineSettings to allow local file access.
    """

    # Qt's built-in qwebchannel.js resource URL
    QWEBCHANNEL_JS_URL = "qrc:///qtwebchannel/qwebchannel.js"

    def __init__(self, bridge: POSBridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.setWindowTitle("Prost POS - نظام البيع")
        self.setMinimumSize(1280, 800)
        self.showMaximized()

        # ── Layout ────────────────────────────────────────────────────────────
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central)

        # ── Web view ─────────────────────────────────────────────────────────
        self.web_view = QWebEngineView(central)
        layout.addWidget(self.web_view)

        page = self.web_view.page()

        # ── Settings ─────────────────────────────────────────────────────────
        s = self.web_view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)

        # ── Inject qwebchannel.js before any user script runs ─────────────────
        # Read the JS file content from Qt resources via a temporary QWebEngineView trick,
        # OR use QWebEngineScript injection which is the correct approach.
        self._inject_qwebchannel_script(page)

        # ── WebChannel ───────────────────────────────────────────────────────
        self.channel = QWebChannel(self)
        self.channel.registerObject("backend", self.bridge)
        page.setWebChannel(self.channel)

        # ── Load frontend ────────────────────────────────────────────────────
        self.load_frontend()

    def _inject_qwebchannel_script(self, page):
        """
        Inject Qt's qwebchannel.js into every page before the document body is parsed.
        This makes window.QWebChannel available globally before React mounts.
        """
        script = QWebEngineScript()
        script.setName("qwebchannel_inject")
        script.setSourceUrl(QUrl(self.QWEBCHANNEL_JS_URL))
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        page.scripts().insert(script)
        logger.info("Injected qwebchannel.js at DocumentCreation via QWebEngineScript.")

    def load_frontend(self):
        """Detect environment and load the correct URL."""
        dev_mode = os.environ.get("POS_DEV_MODE", "0") == "1"

        if dev_mode:
            url_str = "http://localhost:5173"
            logger.info("WebShell — DEV mode: %s", url_str)
        else:
            if getattr(sys, "frozen", False):
                base_path = sys._MEIPASS  # type: ignore[attr-defined]
            else:
                # project_root/broast_pos/ui/web_shell.py  →  project_root
                base_path = os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )

            dist_path = os.path.normpath(
                os.path.join(base_path, "frontend", "dist", "index.html")
            )

            if not os.path.exists(dist_path):
                logger.error("Frontend bundle not found: %s", dist_path)
                QMessageBox.critical(
                    self,
                    "خطأ فادح",
                    f"لم يتم العثور على ملفات واجهة المستخدم.\nمسار البحث:\n{dist_path}\n\nقم بتشغيل: cd frontend && npm run build",
                )
                return

            url_str = QUrl.fromLocalFile(dist_path).toString()
            logger.info("WebShell — PROD mode: %s", url_str)

        self.web_view.load(QUrl(url_str))

    def closeEvent(self, event):
        logger.info("WebShell closing.")
        if self.bridge:
            try:
                self.bridge.dispatch("logout", "")
            except Exception:
                pass
        event.accept()
