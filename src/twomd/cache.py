"""Comprobación conservadora de resultados locales anteriores."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path


def file_hash(path: Path, check_cancelled: Callable[[], None] | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            if check_cancelled is not None:
                check_cancelled()
            digest.update(chunk)
    return digest.hexdigest()


def output_hashes(output: Path, markdown: Path) -> dict[str, str]:
    files = [markdown]
    for folder in ("assets", "diagrams"):
        directory = output / folder
        if directory.is_dir():
            files.extend(sorted(path for path in directory.rglob("*") if path.is_file()))
    return {path.relative_to(output).as_posix(): file_hash(path) for path in files}


def model_files_hash(directory: Path, check_cancelled: Callable[[], None]) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in directory.rglob("*") if path.is_file())
    if not files:
        raise ValueError("La carpeta de modelos está vacía.")
    for path in files:
        check_cancelled()
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(bytes.fromhex(file_hash(path, check_cancelled)))
    return digest.hexdigest()


def read_cached_result(
    output: Path, source: Path, source_hash: str, docling_version: str, config_hash: str
) -> tuple[Path, tuple[str, ...]] | None:
    report_file = output / "conversion-report.json"
    if not report_file.is_file():
        return None
    try:
        report = json.loads(report_file.read_text(encoding="utf-8"))
        if (
            report["archivo_original"] != str(source)
            or report["sha256"] != source_hash
            or report["version_docling"] != docling_version
            or report["configuracion_hash"] != config_hash
            or report["version_cache"] != 1
            or report["estado"] not in ("completado", "completado_con_advertencias")
        ):
            return None
        files = report["archivos"]
        if not isinstance(files, dict) or not files:
            return None
        root = output.resolve()
        for name, digest in files.items():
            path = (output / name).resolve()
            if not path.is_relative_to(root) or not path.is_file() or file_hash(path) != digest:
                return None
        markdown = (output / report["markdown"]).resolve()
        if not markdown.is_relative_to(root) or report["markdown"] not in files:
            return None
        warnings = report["advertencias"]
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            return None
        return markdown, tuple(warnings)
    except (OSError, ValueError, KeyError, TypeError):
        return None
