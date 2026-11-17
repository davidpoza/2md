"""Revisión de imágenes exportadas sin modificar el original."""

import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from twomd.cache import output_hashes

_IMAGE = re.compile(r"!\[[^\]\n]*\]\(([^)\n]+)\)")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)")


@dataclass(frozen=True)
class PictureReference:
    image: Path
    markdown_link: str
    context: str
    index: int
    start: int
    end: int


@dataclass(frozen=True)
class StoredDiagram:
    code: str
    pending: bool


def picture_references(markdown: Path) -> list[PictureReference]:
    text = markdown.read_text(encoding="utf-8")
    root = markdown.parent.resolve()
    assets = (root / "assets").resolve()
    if not assets.is_relative_to(root):
        raise ValueError("La carpeta de imágenes está fuera de la salida.")
    result = []
    offset = 0
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        marker = _FENCE.match(line)
        if fence is not None:
            if (
                marker
                and marker.group(1)[0] == fence[0]
                and len(marker.group(1)) >= len(fence)
                and not marker.group(2).strip()
            ):
                fence = None
            offset += len(line)
            continue
        if marker and (marker.group(1)[0] != "`" or "`" not in marker.group(2)):
            fence = marker.group(1)
            offset += len(line)
            continue
        for match in _IMAGE.finditer(line):
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
            start = offset + match.start()
            end = offset + match.end()
            result.append(
                PictureReference(
                    image=image,
                    markdown_link=match.group(0),
                    context=text[max(0, start - 1500) : end + 1500],
                    index=len(result) + 1,
                    start=start,
                    end=end,
                )
            )
        offset += len(line)
    return result


def _pending_block(index: int, code: str) -> str:
    return (
        f"\n\n<!-- 2MD:mermaid-pendiente:{index} -->\n"
        "> **Diagrama generado por IA: pendiente de revisión.**\n\n"
        f"```mermaid\n{code}\n```\n"
        f"<!-- /2MD:mermaid-pendiente:{index} -->"
    )


def stored_diagram(markdown: Path, reference: PictureReference) -> StoredDiagram | None:
    text = markdown.read_text(encoding="utf-8")
    references = picture_references(markdown)
    if reference.index > len(references) or references[reference.index - 1] != reference:
        raise ValueError("El Markdown ha cambiado; vuelve a abrir la revisión.")
    path = markdown.parent / "diagrams" / f"diagram-{reference.index:03d}.mmd"
    if not path.resolve().is_relative_to(markdown.parent.resolve()):
        raise ValueError("El archivo de diagrama está fuera de la salida.")
    if not path.is_file():
        return None
    code = path.read_text(encoding="utf-8").strip()
    if code and text[reference.end :].startswith(_pending_block(reference.index, code)):
        return StoredDiagram(code, pending=True)
    if code and text[reference.end :].startswith(f"\n\n```mermaid\n{code}\n```"):
        return StoredDiagram(code, pending=False)
    return None


def pending_diagram(markdown: Path, reference: PictureReference) -> str | None:
    diagram = stored_diagram(markdown, reference)
    return diagram.code if diagram is not None and diagram.pending else None


def _atomic_write(path: Path, content: str) -> None:
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
        for attempt in range(5):
            try:
                os.replace(temporary_path, path)
                break
            except OSError as error:
                if getattr(error, "winerror", None) not in (5, 32, 33) or attempt == 4:
                    raise
                time.sleep(0.1 * 2**attempt)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def accept_diagram(
    markdown: Path,
    reference: PictureReference,
    code: str,
    model: str | None = None,
    *,
    pending: bool = False,
) -> Path:
    code = code.strip()
    if not code or "```" in code:
        raise ValueError("El código Mermaid está vacío o contiene delimitadores Markdown.")
    text = markdown.read_text(encoding="utf-8")
    references = picture_references(markdown)
    if reference.index > len(references) or references[reference.index - 1] != reference:
        raise ValueError("El Markdown ha cambiado; vuelve a abrir la revisión.")
    report_path = markdown.parent / "conversion-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    diagrams = markdown.parent / "diagrams"
    diagrams.mkdir(exist_ok=True)
    if not diagrams.resolve().is_relative_to(markdown.parent.resolve()):
        raise ValueError("La carpeta de diagramas está fuera de la salida.")
    diagram_path = diagrams / f"diagram-{reference.index:03d}.mmd"
    previous = stored_diagram(markdown, reference)
    if diagram_path.exists() and (pending or previous is None):
        raise FileExistsError("Ya existe un diagrama para esta imagen; no se sobrescribirá.")

    insertion = _pending_block(reference.index, code) if pending else f"\n\n```mermaid\n{code}\n```"
    old_block = ""
    if previous is not None:
        old_block = (
            _pending_block(reference.index, previous.code)
            if previous.pending
            else f"\n\n```mermaid\n{previous.code}\n```"
        )
    updated = text[: reference.end] + insertion + text[reference.end + len(old_block) :]
    if previous is None:
        with diagram_path.open("x", encoding="utf-8", newline="\n") as file:
            file.write(code + "\n")
    else:
        _atomic_write(diagram_path, code + "\n")
    try:
        _atomic_write(markdown, updated)
        if previous is None:
            report["diagramas"] = int(report["diagramas"]) + 1
            report["diagramas_convertidos"] = int(report["diagramas_convertidos"]) + 1
        report["diagramas_pendientes_revision"] = int(
            report.get("diagramas_pendientes_revision", 0)
        ) + (1 if pending else -1 if previous is not None and previous.pending else 0)
        if model:
            report["modelo_ia"] = model
        report["archivos"] = output_hashes(markdown.parent, markdown)
        _atomic_write(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    except Exception as error:
        try:
            _atomic_write(markdown, text)
            if previous is None:
                diagram_path.unlink(missing_ok=True)
            else:
                _atomic_write(diagram_path, previous.code + "\n")
        except OSError as rollback_error:
            raise RuntimeError(
                "La revisión falló y no pudo restaurarse completamente; "
                "comprueba el Markdown, el informe y el archivo Mermaid."
            ) from rollback_error
        raise RuntimeError(
            "No se pudo guardar la revisión; se restauró el Markdown anterior."
        ) from error
    return diagram_path
