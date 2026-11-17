import json
from pathlib import Path

import pytest
from PIL import Image

from twomd.cache import output_hashes
from twomd.review import accept_diagram, picture_references


@pytest.fixture
def output(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    Image.new("RGB", (4, 4), "white").save(assets / "image.png")
    markdown = tmp_path / "doc.md"
    markdown.write_text("Texto\n\n![imagen](assets/image.png)\n", encoding="utf-8")
    report = {
        "diagramas": 0,
        "diagramas_convertidos": 0,
        "modelo_ia": None,
    }
    (tmp_path / "conversion-report.json").write_text(json.dumps(report), encoding="utf-8")
    return markdown


def test_accept_preserves_original_and_updates_report(output):
    reference = picture_references(output)[0]
    original = reference.image.read_bytes()
    result = accept_diagram(output, reference, "flowchart LR\n A --> B", "modelo")
    text = output.read_text(encoding="utf-8")
    report = json.loads((output.parent / "conversion-report.json").read_text(encoding="utf-8"))
    assert "![imagen](assets/image.png)" in text
    assert "```mermaid\nflowchart LR\n A --> B\n```" in text
    assert result.read_text(encoding="utf-8") == "flowchart LR\n A --> B\n"
    assert reference.image.read_bytes() == original
    assert report["diagramas_convertidos"] == 1
    assert report["modelo_ia"] == "modelo"
    assert report["archivos"] == output_hashes(output.parent, output)


def test_review_rejects_stale_or_repeated_reference(output):
    reference = picture_references(output)[0]
    output.write_text(
        output.read_text(encoding="utf-8") + reference.markdown_link, encoding="utf-8"
    )
    with pytest.raises(ValueError):
        accept_diagram(output, reference, "flowchart LR\n A --> B")
    assert not (output.parent / "diagrams").exists()


def test_failed_report_write_rolls_back(output, monkeypatch):
    from twomd import review

    reference = picture_references(output)[0]
    original = output.read_text(encoding="utf-8")
    write = review._atomic_write

    def fail_report(path: Path, content: str) -> None:
        if path.name == "conversion-report.json":
            raise OSError("error simulado")
        write(path, content)

    monkeypatch.setattr(review, "_atomic_write", fail_report)
    with pytest.raises(RuntimeError, match="restauró"):
        accept_diagram(output, reference, "flowchart LR\n A --> B")
    assert output.read_text(encoding="utf-8") == original
    assert not (output.parent / "diagrams" / "diagram-001.mmd").exists()


def test_atomic_write_retries_transient_windows_denial(output, monkeypatch):
    from twomd import review

    replace = review.os.replace
    attempts = 0

    def temporarily_locked(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            error = PermissionError("bloqueo temporal")
            error.winerror = 5
            raise error
        replace(source, destination)

    monkeypatch.setattr(review.os, "replace", temporarily_locked)
    monkeypatch.setattr(review.time, "sleep", lambda _: None)
    review._atomic_write(output, "actualizado")
    assert attempts == 3
    assert output.read_text(encoding="utf-8") == "actualizado"


def test_atomic_write_preserves_original_after_persistent_denial(output, monkeypatch):
    from twomd import review

    original = output.read_text(encoding="utf-8")
    attempts = 0

    def locked(source, destination):
        nonlocal attempts
        attempts += 1
        error = PermissionError("acceso denegado")
        error.winerror = 5
        raise error

    monkeypatch.setattr(review.os, "replace", locked)
    monkeypatch.setattr(review.time, "sleep", lambda _: None)
    with pytest.raises(PermissionError):
        review._atomic_write(output, "actualizado")
    assert attempts == 5
    assert output.read_text(encoding="utf-8") == original
    assert not list(output.parent.glob("tmp*"))


def test_only_local_assets_are_reviewable(output):
    output.write_text(
        "![fuera](../externo.png)\n![remota](https://example.com/image.png)\n"
        "![local](assets/image.png)",
        encoding="utf-8",
    )
    assert len(picture_references(output)) == 1


def test_images_inside_code_blocks_are_not_reviewed(output):
    output.write_text(
        "![local](assets/image.png)\n\n```mermaid\n"
        'flowchart LR\nA["![ejemplo](assets/image.png)"]\n```\n',
        encoding="utf-8",
    )
    assert len(picture_references(output)) == 1
