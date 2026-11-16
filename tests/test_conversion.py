import hashlib
import json
import re
from importlib.metadata import version
from pathlib import Path

import pytest
from docx import Document
from PIL import Image, ImageDraw

from twomd.conversion import convert_document


def test_docx_exports_text_and_referenced_image(tmp_path):
    source = tmp_path / "origen.docx"
    image = tmp_path / "imagen.png"
    Image.new("RGB", (20, 20), "red").save(image)
    document = Document()
    document.add_heading("Título de ejemplo", level=1)
    document.add_paragraph("Texto funcional.")
    document.add_picture(str(image))
    document.save(source)
    destination = tmp_path / "salida"
    destination.mkdir()

    outcome = convert_document(source, destination)
    markdown = outcome.markdown.read_text(encoding="utf-8")
    assert "Título de ejemplo" in markdown
    assert "Texto funcional." in markdown
    image_paths = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", markdown)
    assert image_paths
    assert all(not Path(path).is_absolute() for path in image_paths)
    assert all((outcome.markdown.parent / path).is_file() for path in image_paths)
    assert source.exists()
    report = json.loads(
        (outcome.markdown.parent / "conversion-report.json").read_text(encoding="utf-8")
    )
    assert report["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert report["imagenes"] >= 1


def test_existing_output_is_not_overwritten(tmp_path):
    source = tmp_path / "origen.docx"
    source.touch()
    destination = tmp_path / "salida"
    destination.mkdir()
    path_hash = hashlib.sha256(str(source.resolve()).casefold().encode("utf-8")).hexdigest()[:12]
    content_hash = hashlib.sha256(b"").hexdigest()[:12]
    config = f"2md-v1:{version('docling')}:{version('docling-core')}:scale=2:"
    config_hash = hashlib.sha256(config.encode("utf-8")).hexdigest()[:12]
    output = destination / f"origen-{path_hash}-{content_hash}-{config_hash}"
    output.mkdir()
    existing = output / "origen.md"
    existing.write_text("existente", encoding="utf-8")

    with pytest.raises(FileExistsError):
        convert_document(source, destination)
    assert existing.read_text(encoding="utf-8") == "existente"


def _text_pdf(path: Path) -> None:
    stream = b"BT /F1 18 Tf 60 740 Td (Texto PDF seleccionable) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    data = b"%PDF-1.4\n"
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(data)
    data += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    data += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    data += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    path.write_bytes(data)


@pytest.mark.parametrize("scanned", [False, True])
def test_pdf_without_ocr(tmp_path, scanned):
    models = Path(__file__).resolve().parents[1] / "resources" / "models"
    if not (models / "docling-project--docling-layout-heron" / "model.safetensors").is_file():
        pytest.skip("Modelos locales de Docling no instalados")
    if not (
        models / "docling-project--docling-models" / "model_artifacts" / "tableformer"
    ).is_dir():
        pytest.skip("Modelos de tablas de Docling no instalados")
    source = tmp_path / "origen.pdf"
    if scanned:
        image = Image.new("RGB", (612, 792), "white")
        ImageDraw.Draw(image).text((60, 60), "Texto PDF escaneado", fill="black")
        image.save(source, "PDF")
    else:
        _text_pdf(source)
    destination = tmp_path / "salida"
    destination.mkdir()

    outcome = convert_document(source, destination, models_directory=models)
    content = outcome.markdown.read_text(encoding="utf-8")
    assert any("OCR desactivado" in warning for warning in outcome.warnings)
    if scanned:
        assert "Texto PDF escaneado" not in content
    else:
        assert "Texto PDF seleccionable" in content
    report = json.loads(
        (outcome.markdown.parent / "conversion-report.json").read_text(encoding="utf-8")
    )
    assert report["estado"] == "completado_con_advertencias"
    assert report["advertencias"] == list(outcome.warnings)
