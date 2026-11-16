import json

from PIL import Image
from PySide6.QtCore import Qt

from twomd.config import Settings
from twomd.ui.review_dialog import ReviewDialog


def test_review_requires_validation_again_after_edit(tmp_path, qtbot, monkeypatch):
    from twomd.ui import review_dialog

    assets = tmp_path / "assets"
    assets.mkdir()
    image = assets / "image.png"
    Image.new("RGB", (4, 4), "white").save(image)
    markdown = tmp_path / "documento.md"
    markdown.write_text("![imagen](assets/image.png)", encoding="utf-8")
    (tmp_path / "conversion-report.json").write_text(
        json.dumps({"diagramas": 0, "diagramas_convertidos": 0}), encoding="utf-8"
    )
    monkeypatch.setattr(review_dialog, "render_mermaid", lambda code: image.read_bytes())
    dialog = ReviewDialog(markdown, Settings(), None)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.editor.setPlainText("flowchart LR\nA-->B")
    assert not dialog.accept_button.isEnabled()
    qtbot.mouseClick(dialog.validate, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(dialog.accept_button.isEnabled, timeout=10000)
    dialog.editor.appendPlainText("B-->C")
    assert not dialog.accept_button.isEnabled()
