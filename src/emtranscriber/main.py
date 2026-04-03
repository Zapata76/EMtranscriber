from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QResource
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from emtranscriber.bootstrap import build_container
from emtranscriber.shared.i18n import detect_system_language
from emtranscriber.shared.theme import apply_theme
from emtranscriber.ui.windows.main_window import MainWindow


def _ensure_console_streams() -> None:
    """Provide no-op text streams when running in windowed/frozen mode."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _branding_rcc_candidates() -> list[Path]:
    module_resources = Path(__file__).resolve().parent / "ui" / "resources" / "branding.rcc"
    candidates: list[Path] = [module_resources]

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates = [
            exe_dir / "emtranscriber" / "ui" / "resources" / "branding.rcc",
            exe_dir / "_internal" / "emtranscriber" / "ui" / "resources" / "branding.rcc",
            exe_dir / "branding.rcc",
            *candidates,
        ]

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _register_branding_resources() -> tuple[bool, list[Path]]:
    candidates = _branding_rcc_candidates()
    for candidate in candidates:
        if not candidate.exists():
            continue
        if QResource.registerResource(str(candidate)):
            return True, candidates
    return False, candidates


def main() -> int:
    _ensure_console_streams()

    app = QApplication(sys.argv)
    loaded, candidates = _register_branding_resources()
    if not loaded:
        QMessageBox.critical(
            None,
            "EMtranscriber startup error",
            "Unable to load UI branding resources.\n\nSearched paths:\n"
            + "\n".join(str(path) for path in candidates),
        )
        return 1

    app_icon = QIcon(":/branding/icon")
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    try:
        container = build_container()
    except Exception as exc:  # noqa: BLE001
        lang = detect_system_language()
        title_by_lang = {
            "it": "Errore avvio EMtranscriber",
            "es": "Error de inicio de EMtranscriber",
            "de": "EMtranscriber Startfehler",
            "fr": "Erreur de demarrage EMtranscriber",
        }
        text_by_lang = {
            "it": "Impossibile inizializzare il runtime dell'applicazione.",
            "es": "No se puede inicializar el runtime de la aplicacion.",
            "de": "Die Laufzeitumgebung der Anwendung konnte nicht initialisiert werden.",
            "fr": "Impossible d'initialiser le runtime de l'application.",
        }
        details_by_lang = {
            "it": "Dettagli",
            "es": "Detalles",
            "de": "Details",
            "fr": "Details",
        }

        title = title_by_lang.get(lang, "EMtranscriber startup error")
        message = text_by_lang.get(lang, "Unable to initialize application runtime.")
        details = details_by_lang.get(lang, "Details")

        QMessageBox.critical(
            None,
            title,
            f"{message}\n\n{details}: {exc}",
        )
        return 1

    apply_theme(app, container.settings.ui_theme)
    app.setApplicationName(container.translator.t("app.name"))

    window = MainWindow(container)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
