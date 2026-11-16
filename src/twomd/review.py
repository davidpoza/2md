"""Revisión de imágenes exportadas sin modificar el original."""

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from twomd.cache import output_hashes

_IMAGE = re.compile(r"!\[[^\]\n]*\]\(([^)\n]+)\)")


@dataclass(frozen=True)
class PictureReference:
    image: Path
    markdown_link: str
    context: str
    index: int


def picture_references(markdown: Path) -> list[PictureReference]:
    text = markdown.read_text(encoding="utf-8")
    root = markdown.parent.resolve()
    assets = (root / "assets").resolve()
    if not assets.is_relative_to(root):
        raise ValueError("La carpeta de imágenes está fuera de la salida.")
    result = []
    for match in _IMAGE.finditer(text):
        parsed = urlsplit(match.group(1))
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            continue
        image = (root / unquote(parsed.path)).resolve()
        if (
            not image.is_relative_to(assets)
            or not image.is_relative_to(root)
            or not image.is_file()
        ):
            continue
        result.append(
            PictureReference(
                image=image,
                markdown_link=match.group(0),
                context=text[max(0, match.start() - 1500) : match.end() + 1500],
                index=len(result) + 1,
            )
        )
    return result


def _atomic_write(path: Path, content: str) -> None:
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def accept_diagram(
    markdown: Path, reference: PictureReference, code: str, model: str | None = None
) -> Path:
    code = code.strip()
    if not code or "```" in code:
        raise ValueError("El código Mermaid está vacío o contiene delimitadores Markdown.")
    text = markdown.read_text(encoding="utf-8")
    references = picture_references(markdown)
    if reference.index > len(references) or references[reference.index - 1] != reference:
        raise ValueError("El Markdown ha cambiado; vuelve a abrir la revisión.")
    if text.count(reference.markdown_link) != 1:
        raise ValueError("La imagen aparece varias veces; no se puede asociar sin ambigüedad.")
    report_path = markdown.parent / "conversion-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    diagrams = markdown.parent / "diagrams"
    diagrams.mkdir(exist_ok=True)
    if not diagrams.resolve().is_relative_to(markdown.parent.resolve()):
        raise ValueError("La carpeta de diagramas está fuera de la salida.")
    diagram_path = diagrams / f"diagram-{reference.index:03d}.mmd"
    if diagram_path.exists():
        raise FileExistsError("Ya existe un diagrama para esta imagen; no se sobrescribirá.")

    updated = text.replace(
        reference.markdown_link,
        f"{reference.markdown_link}\n\n```mermaid\n{code}\n```",
        1,
    )
    with diagram_path.open("x", encoding="utf-8", newline="\n") as file:
        file.write(code + "\n")
    try:
        _atomic_write(markdown, updated)
        report["diagramas"] = int(report["diagramas"]) + 1
        report["diagramas_convertidos"] = int(report["diagramas_convertidos"]) + 1
        if model:
            report["modelo_ia"] = model
        report["archivos"] = output_hashes(markdown.parent, markdown)
        _atomic_write(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    except Exception as error:
        try:
            _atomic_write(markdown, text)
            diagram_path.unlink(missing_ok=True)
        except OSError as rollback_error:
            raise RuntimeError(
                "La revisión falló y no pudo restaurarse completamente; "
                "comprueba el Markdown, el informe y el archivo Mermaid."
            ) from rollback_error
        raise RuntimeError(
            "No se pudo guardar la revisión; se restauró el Markdown anterior."
        ) from error
    return diagram_path
