"""Conversión local de un documento mediante Xberg."""

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from threading import Event

from twomd import __version__
from twomd.cache import output_hashes, read_cached_result


class ConversionCancelled(Exception):
    pass


_IMAGE_REFERENCE = re.compile(r"!\[([^\]]*)\]\(embedded:([^)]+)\)")
_IMAGE_EXTENSIONS = {"bmp", "gif", "jpeg", "jpg", "png", "svg", "tif", "tiff", "webp"}


@dataclass(frozen=True)
class ConversionOutcome:
    markdown: Path
    warnings: tuple[str, ...]
    retryable: bool = False


def convert_document(
    source: Path,
    destination: Path,
    cancel: Event | None = None,
    cache_variant: str = "",
) -> ConversionOutcome:
    from xberg import (
        ExtractInput,
        ExtractionConfig,
        ImageExtractionConfig,
        PdfConfig,
        extract,
    )

    source = source.resolve(strict=True)
    if source.suffix.lower() not in {".docx", ".pdf"} or not source.is_file():
        raise ValueError("El archivo debe ser un documento DOCX o PDF existente.")
    if not destination.is_dir():
        raise ValueError("La carpeta de destino no existe.")

    started = time.monotonic()
    cancel = cancel if cancel is not None else Event()

    def check_cancelled() -> None:
        if cancel.is_set():
            raise ConversionCancelled("Conversión cancelada.")

    check_cancelled()
    digest = hashlib.sha256()
    original_stat = source.stat()
    with source.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            check_cancelled()
            digest.update(chunk)
    source_hash = digest.hexdigest()
    hashed_stat = source.stat()
    if (original_stat.st_size, original_stat.st_mtime_ns) != (
        hashed_stat.st_size,
        hashed_stat.st_mtime_ns,
    ):
        raise RuntimeError("El archivo original cambió durante el cálculo del hash.")
    xberg_version = version("xberg")
    config = f"2md-v2:{xberg_version}:output=markdown:ocr=off:images=referenced:"
    if source.suffix.lower() == ".pdf":
        config += "pdf-images=on:"
    if cache_variant:
        config += f":diagramas={cache_variant}"
    config_hash = hashlib.sha256(config.encode()).hexdigest()
    check_cancelled()
    path_hash = hashlib.sha256(str(source).casefold().encode("utf-8")).hexdigest()[:12]
    output = destination / f"{source.stem}-{path_hash}-{source_hash[:12]}-{config_hash[:12]}"
    if output.exists():
        cached = read_cached_result(output, source, source_hash, xberg_version, config_hash)
        if cached is None:
            raise FileExistsError(
                f"Ya existe una carpeta de salida no reutilizable en «{output}». "
                "No se sobrescribirá."
            )
        return ConversionOutcome(markdown=cached[0], warnings=cached[1])
    extraction_config = ExtractionConfig(
        use_cache=False,
        disable_ocr=True,
        ocr_embedded_images=False,
        output_format="markdown",
        images=ImageExtractionConfig(
            extract_images=True,
            inject_placeholders=True,
            run_ocr_on_images=False,
            append_ocr_text=False,
        ),
        pdf_options=PdfConfig(extract_images=True, ocr_inline_images=False),
    )
    result = asyncio.run(
        extract(ExtractInput(kind="uri", uri=str(source)), extraction_config)
    )
    if cancel.is_set():
        raise ConversionCancelled("Conversión cancelada después de la extracción.")
    after_stat = source.stat()
    if (original_stat.st_size, original_stat.st_mtime_ns) != (
        after_stat.st_size,
        after_stat.st_mtime_ns,
    ):
        raise RuntimeError("El archivo original cambió durante la conversión.")
    if not result.results:
        messages = "; ".join(error.message for error in result.errors)
        raise RuntimeError(f"Xberg no pudo convertir el documento. {messages}".strip())

    warnings = []
    if source.suffix.lower() == ".pdf":
        warnings.append(
            "OCR desactivado: no se extraerá texto de imágenes ni de páginas escaneadas."
        )
    warnings.extend(f"Xberg: {error.message}" for error in result.errors)
    document = result.results[0]
    images = document.images or []
    missing = sum(not image.data for image in images)
    if missing:
        warnings.append(f"No se pudieron recuperar {missing} imágenes del documento.")

    output.mkdir()
    markdown = output / f"{source.stem}.md"
    try:
        assets = output / "assets"
        image_references: dict[str, str] = {}
        for index, image in enumerate(images, start=1):
            if not image.data:
                continue
            extension = (image.format or "").lower().lstrip(".")
            suffix = extension if extension in _IMAGE_EXTENSIONS else "bin"
            relative_path = Path("assets") / f"image-{index:04d}.{suffix}"
            assets.mkdir(exist_ok=True)
            (output / relative_path).write_bytes(image.data)
            page_number = image.page_number or 1
            image_references[f"p{page_number}_i{image.image_index}"] = (
                relative_path.as_posix()
            )

        def replace_image_reference(match: re.Match[str]) -> str:
            relative_path = image_references.get(match.group(2))
            if relative_path is None:
                return match.group(1)
            return f"![{match.group(1)}]({relative_path})"

        content = _IMAGE_REFERENCE.sub(replace_image_reference, document.content)
        markdown.write_text(content, encoding="utf-8")
        report = {
            "archivo_original": str(source),
            "sha256": source_hash,
            "fecha": datetime.now(UTC).isoformat(),
            "estado": "completado_con_advertencias" if warnings else "completado",
            "version_2md": __version__,
            "version_xberg": xberg_version,
            "configuracion_hash": config_hash,
            "version_cache": 2,
            "modelo_ia": None,
            "imagenes": len(images),
            "diagramas": 0,
            "diagramas_convertidos": 0,
            "diagramas_pendientes_revision": 0,
            "errores": [],
            "advertencias": warnings,
            "duracion_segundos": round(time.monotonic() - started, 3),
            "markdown": markdown.name,
            "archivos": output_hashes(output, markdown),
        }
        (output / "conversion-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as error:
        raise RuntimeError(
            f"No se pudo exportar Markdown. La carpeta incompleta se conserva en «{output}»: "
            f"{error}"
        ) from error
    return ConversionOutcome(markdown=markdown, warnings=tuple(warnings))
