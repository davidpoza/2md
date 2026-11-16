"""Selección de documentos, independiente de la interfaz."""

from pathlib import Path

SUPPORTED_EXTENSIONS = {".docx", ".pdf"}


def supported_documents(paths: list[Path]) -> list[Path]:
    """Devuelve archivos admitidos y únicos, conservando el orden de entrada."""
    documents = []
    seen = set()
    for path in paths:
        resolved = path.resolve()
        if resolved.is_file() and resolved.suffix.lower() in SUPPORTED_EXTENSIONS:
            key = str(resolved).casefold()
            if key not in seen:
                documents.append(resolved)
                seen.add(key)
    return documents
