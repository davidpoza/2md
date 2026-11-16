"""Conversión local de un documento mediante Docling."""

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from threading import Event

from twomd import __version__
from twomd.cache import model_files_hash, output_hashes, read_cached_result


class ConversionCancelled(Exception):
    pass


@dataclass(frozen=True)
class ConversionOutcome:
    markdown: Path
    warnings: tuple[str, ...]
    retryable: bool = False


def convert_document(
    source: Path,
    destination: Path,
    cancel: Event | None = None,
    models_directory: Path | None = None,
    cache_variant: str = "",
) -> ConversionOutcome:
    from docling.datamodel.base_models import ConversionStatus, InputFormat
    from docling.datamodel.pipeline_options import (
        LayoutObjectDetectionOptions,
        PdfPipelineOptions,
        TableFormerMode,
        TableStructureOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling_core.types.doc import ImageRefMode

    source = source.resolve(strict=True)
    if source.suffix.lower() not in {".docx", ".pdf"} or not source.is_file():
        raise ValueError("El archivo debe ser un documento DOCX o PDF existente.")
    if not destination.is_dir():
        raise ValueError("La carpeta de destino no existe.")
    if source.suffix.lower() == ".pdf" and (
        models_directory is None or not models_directory.is_dir()
    ):
        raise ValueError("Selecciona una carpeta válida de modelos locales de Docling.")

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
    docling_version = version("docling")
    core_version = version("docling-core")
    model_hash = (
        model_files_hash(models_directory, check_cancelled)
        if source.suffix.lower() == ".pdf" and models_directory is not None
        else ""
    )
    config = f"2md-v1:{docling_version}:{core_version}:scale=2:{model_hash}"
    if source.suffix.lower() == ".pdf":
        config += ":ocr=off"
    if cache_variant:
        config += f":diagramas={cache_variant}"
    config_hash = hashlib.sha256(config.encode()).hexdigest()
    check_cancelled()
    path_hash = hashlib.sha256(str(source).casefold().encode("utf-8")).hexdigest()[:12]
    output = destination / f"{source.stem}-{path_hash}-{source_hash[:12]}-{config_hash[:12]}"
    if output.exists():
        cached = read_cached_result(output, source, source_hash, docling_version, config_hash)
        if cached is None:
            raise FileExistsError(
                f"Ya existe una carpeta de salida no reutilizable en «{output}». "
                "No se sobrescribirá."
            )
        return ConversionOutcome(markdown=cached[0], warnings=cached[1])
    options = PdfPipelineOptions(
        do_ocr=False,
        generate_picture_images=True,
        images_scale=2.0,
        enable_remote_services=False,
        artifacts_path=models_directory,
        layout_options=LayoutObjectDetectionOptions.from_preset("layout_heron_default"),
        table_structure_options=TableStructureOptions(mode=TableFormerMode.ACCURATE),
    )
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.DOCX],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )
    result = converter.convert(source, raises_on_error=False)
    if cancel.is_set():
        raise ConversionCancelled("Conversión cancelada después de la extracción.")
    after_stat = source.stat()
    if (original_stat.st_size, original_stat.st_mtime_ns) != (
        after_stat.st_size,
        after_stat.st_mtime_ns,
    ):
        raise RuntimeError("El archivo original cambió durante la conversión.")
    if result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
        messages = "; ".join(error.error_message for error in result.errors)
        raise RuntimeError(f"Docling no pudo convertir el documento. {messages}".strip())

    warnings = []
    if source.suffix.lower() == ".pdf":
        warnings.append(
            "OCR desactivado: no se extraerá texto de imágenes ni de páginas escaneadas."
        )
    if result.status == ConversionStatus.PARTIAL_SUCCESS:
        warnings.append("Docling informó de una conversión parcial; revisa el resultado.")
    warnings.extend(error.error_message for error in result.errors)
    missing = sum(
        picture.get_image(result.document) is None for picture in result.document.pictures
    )
    if missing:
        warnings.append(f"No se pudieron recuperar {missing} imágenes del documento.")

    output.mkdir()
    markdown = output / f"{source.stem}.md"
    try:
        result.document.save_as_markdown(
            markdown,
            artifacts_dir=Path("assets"),
            image_mode=ImageRefMode.REFERENCED,
        )
        report = {
            "archivo_original": str(source),
            "sha256": source_hash,
            "fecha": datetime.now(UTC).isoformat(),
            "estado": "completado_con_advertencias" if warnings else "completado",
            "version_2md": __version__,
            "version_docling": docling_version,
            "configuracion_hash": config_hash,
            "version_cache": 1,
            "modelo_ia": None,
            "imagenes": len(result.document.pictures),
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
