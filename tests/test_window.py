import json

import pytest
from PySide6.QtWidgets import QMessageBox

from twomd.config import AISettings, Settings, load_settings
from twomd.conversion import ConversionOutcome
from twomd.diagrams import DiagramProposal
from twomd.ui.main_window import MainWindow


def test_window_adds_files_once_and_persists_destination(qtbot, tmp_path):
    file = tmp_path / "documento.pdf"
    file.touch()
    path = tmp_path / "config" / "settings.json"
    window = MainWindow(Settings(), path)
    qtbot.addWidget(window)
    window.add_paths([file, file])
    assert window.table.rowCount() == 1
    assert window.table.item(0, 1).text() == "Pendiente"
    assert window.persist(Settings(output_directory=str(tmp_path)))
    assert load_settings(path).output_directory == str(tmp_path)


def test_automatic_diagrams_require_consent(qtbot, tmp_path, monkeypatch):
    from twomd.ui import main_window

    file = tmp_path / "documento.docx"
    file.touch()
    settings = Settings(
        output_directory=str(tmp_path),
        ai=AISettings(enabled=True, base_url="https://example.com/v1", model="vision"),
    )
    window = MainWindow(settings, tmp_path / "settings.json")
    qtbot.addWidget(window)
    window.add_paths([file])
    assert not window.automatic_diagrams.isChecked()
    window.automatic_diagrams.setChecked(True)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    monkeypatch.setattr(main_window, "get_secret", lambda name: pytest.fail("No debe leer claves"))
    window.start_conversion()
    assert not window.pending
    assert not window.workers


def test_automatic_diagrams_run_after_conversion(qtbot, tmp_path, monkeypatch):
    from twomd import automatic_diagrams
    from twomd.ui import conversion_worker, main_window

    source = tmp_path / "documento.docx"
    source.touch()
    output = tmp_path / "output"
    output.mkdir()

    def convert(source, destination, cancel, models, cache_variant=""):
        assert cache_variant
        assets = output / "assets"
        assets.mkdir()
        (assets / "image.png").write_bytes(b"image")
        markdown = output / "documento.md"
        markdown.write_text("![imagen](assets/image.png)", encoding="utf-8")
        (output / "conversion-report.json").write_text(
            json.dumps(
                {
                    "diagramas": 0,
                    "diagramas_convertidos": 0,
                    "diagramas_pendientes_revision": 0,
                    "advertencias": [],
                    "estado": "completado",
                }
            ),
            encoding="utf-8",
        )
        return ConversionOutcome(markdown, ())

    monkeypatch.setattr(conversion_worker, "convert_document", convert)
    monkeypatch.setattr(main_window, "get_secret", lambda name: "clave")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)

    def propose(*args, on_request, on_response):
        on_request()
        on_response(200)
        return DiagramProposal(categoria="flujo", fiable=True, mermaid="flowchart LR\nA-->B")

    monkeypatch.setattr(automatic_diagrams, "propose_diagram", propose)
    monkeypatch.setattr(automatic_diagrams, "render_mermaid", lambda code: b"PNG")
    settings = Settings(
        output_directory=str(tmp_path),
        ai=AISettings(enabled=True, base_url="https://example.com/v1", model="vision"),
    )
    window = MainWindow(settings, tmp_path / "settings.json")
    qtbot.addWidget(window)
    window.add_paths([source])
    window.automatic_diagrams.setChecked(True)
    window.start_conversion()
    qtbot.waitUntil(lambda: window.table.item(0, 1).text() == "Completado", timeout=10000)
    text = (output / "documento.md").read_text(encoding="utf-8")
    assert "![imagen](assets/image.png)" in text
    assert "pendiente de revisión" in text
    assert "```mermaid\nflowchart LR\nA-->B\n```" in text
    assert window.automatic_diagrams.isEnabled()
    activity = window.activity.toPlainText()
    assert "documento.docx" in activity
    assert "Imagen 1/1: solicitud a IA, intento 1" in activity
    assert "Imagen 1/1: respuesta HTTP 200" in activity
    assert "Imagen 1/1: respuesta de IA recibida" in activity
    assert "Imagen 1/1: preparando y validando Mermaid" in activity
    assert "clave" not in activity


def test_settings_reports_ai_connection_attempts(qtbot, monkeypatch):
    from twomd.ui import settings_dialog

    settings = Settings(
        ai=AISettings(enabled=True, base_url="https://example.com/v1", model="vision")
    )
    monkeypatch.setattr(settings_dialog, "get_secret", lambda name: "clave-secreta")
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)

    def check(*args, on_request, on_response):
        on_request()
        on_response(200)

    monkeypatch.setattr(settings_dialog, "check_connection", check)
    dialog = settings_dialog.SettingsDialog(settings, None)
    qtbot.addWidget(dialog)
    messages = []
    dialog.activity.connect(messages.append)
    dialog.start_check("vision")
    qtbot.waitUntil(lambda: dialog.worker is None, timeout=10000)
    assert any("prueba de visión" in message and "intento 1" in message for message in messages)
    assert any("respuesta HTTP 200" in message for message in messages)
    assert any("prueba completada" in message for message in messages)
    assert "clave-secreta" not in "\n".join(messages)
