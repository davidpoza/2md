import json
from threading import Event

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from twomd.config import AISettings, Settings
from twomd.diagrams import DiagramProposal
from twomd.review import accept_diagram, picture_references
from twomd.ui.review_dialog import ReviewDialog

_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600">'
    b'<rect width="800" height="600" fill="white"/>'
    b'<text x="20" y="40">Diagrama</text></svg>'
)


def test_review_requires_validation_again_after_edit(tmp_path, qtbot, monkeypatch):
    from twomd.ui import review_dialog

    assets = tmp_path / "assets"
    assets.mkdir()
    image = assets / "image.png"
    Image.new("RGB", (800, 600), "white").save(image)
    markdown = tmp_path / "documento.md"
    markdown.write_text("![imagen](assets/image.png)", encoding="utf-8")
    (tmp_path / "conversion-report.json").write_text(
        json.dumps({"diagramas": 0, "diagramas_convertidos": 0}), encoding="utf-8"
    )
    monkeypatch.setattr(review_dialog, "render_mermaid", lambda code: _SVG)
    dialog = ReviewDialog(markdown, Settings(), None)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.editor.setPlainText("flowchart LR\nA-->B")
    assert not dialog.accept_button.isEnabled()
    qtbot.mouseClick(dialog.validate, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(dialog.accept_button.isEnabled, timeout=10000)
    qtbot.mouseClick(dialog.fullscreen_button, Qt.MouseButton.LeftButton)
    viewer = dialog.preview_viewer
    qtbot.waitUntil(viewer.isFullScreen)
    assert viewer.view.sceneRect().width() == 800
    qtbot.mouseClick(viewer.actual, Qt.MouseButton.LeftButton)
    assert viewer.view.transform().m11() == pytest.approx(1.0)
    qtbot.mouseClick(viewer.zoom_in, Qt.MouseButton.LeftButton)
    assert viewer.view.transform().m11() == pytest.approx(1.25)
    qtbot.mouseClick(viewer.zoom_out, Qt.MouseButton.LeftButton)
    assert viewer.view.transform().m11() == pytest.approx(1.0)
    qtbot.mouseClick(viewer.fit, Qt.MouseButton.LeftButton)
    assert viewer.view.fitted
    qtbot.keyClick(viewer, Qt.Key.Key_Escape)
    assert not viewer.isVisible()
    dialog.editor.appendPlainText("B-->C")
    assert not dialog.accept_button.isEnabled()
    assert not dialog.fullscreen_button.isEnabled()


def test_review_loads_and_accepts_automatic_proposal(tmp_path, qtbot, monkeypatch):
    from twomd.ui import review_dialog

    assets = tmp_path / "assets"
    assets.mkdir()
    image = assets / "image.png"
    Image.new("RGB", (4, 4), "white").save(image)
    markdown = tmp_path / "documento.md"
    markdown.write_text("![imagen](assets/image.png)", encoding="utf-8")
    report = tmp_path / "conversion-report.json"
    report.write_text(json.dumps({"diagramas": 0, "diagramas_convertidos": 0}), encoding="utf-8")
    accept_diagram(markdown, picture_references(markdown)[0], "flowchart LR\nA-->B", pending=True)
    monkeypatch.setattr(review_dialog, "render_mermaid", lambda code: _SVG)
    dialog = ReviewDialog(markdown, Settings(), None)
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog.editor.toPlainText() == "flowchart LR\nA-->B"
    assert not dialog.accept_button.isEnabled()
    qtbot.mouseClick(dialog.validate, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(dialog.accept_button.isEnabled, timeout=10000)
    qtbot.mouseClick(dialog.accept_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: dialog.worker is None, timeout=10000)
    assert "pendiente de revisión" not in markdown.read_text(encoding="utf-8")
    assert json.loads(report.read_text(encoding="utf-8"))["diagramas_pendientes_revision"] == 0


def test_manual_review_reports_ai_attempts(tmp_path, qtbot, monkeypatch):
    from twomd.ui import review_dialog

    assets = tmp_path / "assets"
    assets.mkdir()
    Image.new("RGB", (4, 4), "white").save(assets / "image.png")
    markdown = tmp_path / "documento.md"
    markdown.write_text("![imagen](assets/image.png)", encoding="utf-8")
    settings = Settings(
        ai=AISettings(enabled=True, base_url="https://example.com/v1", model="vision")
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(review_dialog, "get_secret", lambda name: "clave-secreta")

    def propose(*args, on_request, on_response):
        on_request()
        on_response(200)
        return DiagramProposal(categoria="fotografia", fiable=False)

    monkeypatch.setattr(review_dialog, "propose_diagram", propose)
    dialog = ReviewDialog(markdown, settings, None)
    qtbot.addWidget(dialog)
    messages = []
    dialog.activity.connect(messages.append)
    dialog.generate_proposal()
    qtbot.waitUntil(lambda: dialog.worker is None, timeout=10000)
    assert any("revisión de imagen 1" in message and "intento 1" in message for message in messages)
    assert any("respuesta HTTP 200" in message for message in messages)
    assert any("respuesta de revisión recibida" in message for message in messages)
    assert "clave-secreta" not in "\n".join(messages)


@pytest.mark.parametrize("fails", [False, True])
def test_review_loading_overlay_covers_work_and_clears_after_completion(
    tmp_path, qtbot, monkeypatch, fails
):
    from twomd.ui import review_dialog

    assets = tmp_path / "assets"
    assets.mkdir()
    image = assets / "image.png"
    Image.new("RGB", (4, 4), "white").save(image)
    markdown = tmp_path / "documento.md"
    markdown.write_text("![imagen](assets/image.png)", encoding="utf-8")
    release = Event()

    def render(code):
        if not release.wait(10):
            raise RuntimeError("La prueba no liberó el renderizado.")
        if fails:
            raise RuntimeError("Error de renderizado simulado.")
        return _SVG

    monkeypatch.setattr(review_dialog, "render_mermaid", render)
    dialog = ReviewDialog(markdown, Settings(), None)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.editor.setPlainText("flowchart LR\nA-->B")
    try:
        qtbot.mouseClick(dialog.validate, Qt.MouseButton.LeftButton)
        assert dialog.loading_overlay.isVisible()
        assert "validando Mermaid" in dialog.loading_message.text()
        assert not dialog.close_button.isEnabled()
        dialog.resize(1100, 750)
        qtbot.waitUntil(lambda: dialog.loading_overlay.geometry() == dialog.rect())
    finally:
        release.set()
        qtbot.waitUntil(lambda: dialog.worker is None, timeout=10000)
    assert not dialog.loading_overlay.isVisible()
    assert dialog.close_button.isEnabled()
    assert dialog.editor.isEnabled()
    if fails:
        assert "Error de renderizado simulado" in dialog.message.text()


@pytest.fixture
def review_with_two_images(tmp_path, qtbot, monkeypatch):
    from twomd.ui import review_dialog

    assets = tmp_path / "assets"
    assets.mkdir()
    for name in ("first.png", "second.png"):
        Image.new("RGB", (4, 4), "white").save(assets / name)
    markdown = tmp_path / "documento.md"
    markdown.write_text(
        "![primera](assets/first.png)\n\n![segunda](assets/second.png)\n", encoding="utf-8"
    )
    (tmp_path / "conversion-report.json").write_text(
        json.dumps({"diagramas": 0, "diagramas_convertidos": 0}), encoding="utf-8"
    )
    monkeypatch.setattr(review_dialog, "render_mermaid", lambda code: _SVG)
    dialog = ReviewDialog(markdown, Settings(), None)
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


def test_navigation_preserves_separate_drafts_and_preview(review_with_two_images, qtbot):
    dialog = review_with_two_images
    first_code = "flowchart LR\nA-->B"
    second_code = "sequenceDiagram\nAlice->>Bob: Hola"
    dialog.editor.setPlainText(first_code)
    dialog.proposal_model = "modelo-primero"
    dialog.validate_code()
    qtbot.waitUntil(lambda: dialog.worker is None, timeout=10000)
    assert dialog.preview_svg == _SVG
    dialog.pictures.setCurrentRow(1)
    assert dialog.editor.toPlainText() == ""
    assert dialog.preview_svg is None
    dialog.editor.setPlainText(second_code)
    dialog.pictures.setCurrentRow(0)
    assert dialog.editor.toPlainText() == first_code
    assert dialog.validated_code == first_code
    assert dialog.proposal_model == "modelo-primero"
    assert dialog.preview_svg == _SVG
    assert not dialog.preview.pixmap().isNull()
    assert dialog.fullscreen_button.isEnabled()
    assert dialog.accept_button.isEnabled()
    dialog.pictures.setCurrentRow(1)
    assert dialog.editor.toPlainText() == second_code
    assert dialog.validated_code is None
    assert dialog.preview_svg is None
    assert not dialog.accept_button.isEnabled()


def test_accepted_state_and_preview_survive_navigation_and_edits(review_with_two_images, qtbot):
    dialog = review_with_two_images
    code = "flowchart LR\nA-->B"
    dialog.editor.setPlainText(code)
    dialog.validate_code()
    qtbot.waitUntil(lambda: dialog.worker is None, timeout=10000)
    dialog.save_diagram()
    qtbot.waitUntil(lambda: dialog.worker is None, timeout=10000)
    assert dialog.preview_svg == _SVG
    assert not dialog.pictures.item(0).icon().isNull()
    assert not dialog.accept_button.isEnabled()
    dialog.pictures.setCurrentRow(1)
    assert dialog.pictures.item(1).icon().isNull()
    dialog.pictures.setCurrentRow(0)
    assert dialog.editor.toPlainText() == code
    assert dialog.preview_svg == _SVG
    assert not dialog.pictures.item(0).icon().isNull()
    dialog.editor.appendPlainText("B-->C")
    assert dialog.pictures.item(0).icon().isNull()
    assert dialog.preview_svg is None
    dialog.pictures.setCurrentRow(1)
    dialog.pictures.setCurrentRow(0)
    assert "B-->C" in dialog.editor.toPlainText()
    assert not dialog.accept_button.isEnabled()
    dialog.validate_code()
    qtbot.waitUntil(lambda: dialog.worker is None, timeout=10000)
    dialog.save_diagram()
    qtbot.waitUntil(lambda: dialog.worker is None, timeout=10000)
    assert not dialog.pictures.item(0).icon().isNull()
    assert dialog.markdown.read_text(encoding="utf-8").count("```mermaid") == 1
    reopened = ReviewDialog(dialog.markdown, Settings(), None)
    qtbot.addWidget(reopened)
    assert reopened.editor.toPlainText() == dialog.editor.toPlainText()
    assert not reopened.pictures.item(0).icon().isNull()
