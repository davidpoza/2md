"""Clasificación y generación opcional de diagramas pendientes de revisión."""

import json
from collections.abc import Callable
from itertools import count as counter
from threading import BoundedSemaphore, Event

from twomd.ai import safe_error
from twomd.config import Settings
from twomd.conversion import ConversionCancelled, ConversionOutcome
from twomd.diagrams import propose_diagram
from twomd.mermaid import render_mermaid
from twomd.review import _atomic_write, accept_diagram, pending_diagram, picture_references


def process_automatic_diagrams(
    outcome: ConversionOutcome,
    settings: Settings,
    api_key: str,
    proxy_password: str | None,
    cancel: Event,
    requests: BoundedSemaphore,
    *,
    progress: Callable[[str], None] | None = None,
) -> ConversionOutcome:
    markdown = outcome.markdown
    report_path = markdown.parent / "conversion-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    processed = set(report.get("imagenes_analizadas_ia", []))
    warnings = [
        warning
        for warning in outcome.warnings
        if not warning.startswith("Análisis automático de imagen ")
    ]
    count = len(picture_references(markdown))
    retryable = False

    def notify(message: str) -> None:
        if progress is not None:
            progress(message)

    def persist() -> None:
        current = json.loads(report_path.read_text(encoding="utf-8"))
        current["imagenes_analizadas_ia"] = sorted(processed)
        current["advertencias"] = warnings
        current["estado"] = "completado_con_advertencias" if warnings else "completado"
        _atomic_write(report_path, json.dumps(current, ensure_ascii=False, indent=2) + "\n")

    try:
        for index in range(1, count + 1):
            if cancel.is_set():
                raise ConversionCancelled("Análisis automático cancelado.")
            if index in processed:
                continue
            reference = picture_references(markdown)[index - 1]
            if pending_diagram(markdown, reference) is not None:
                processed.add(index)
                continue
            notify(f"Imagen {index}/{count}: esperando disponibilidad para IA.")
            while not requests.acquire(timeout=0.2):
                if cancel.is_set():
                    raise ConversionCancelled("Análisis automático cancelado.")
            attempts = counter(1)
            try:
                if cancel.is_set():
                    raise ConversionCancelled("Análisis automático cancelado.")
                proposal = propose_diagram(
                    reference.image,
                    reference.context,
                    settings.ai,
                    settings.network,
                    api_key,
                    proxy_password,
                    on_request=lambda index=index, attempts=attempts: notify(
                        f"Imagen {index}/{count}: solicitud a IA, intento {next(attempts)}."
                    ),
                    on_response=lambda status, index=index: notify(
                        f"Imagen {index}/{count}: respuesta HTTP {status} de IA."
                    ),
                )
            except ConversionCancelled:
                raise
            except Exception as error:  # noqa: BLE001
                message = safe_error(error)
                notify(f"Imagen {index}/{count}: error de IA. {message}")
                warnings.append(f"Análisis automático de imagen {index}: {message}")
                retryable = True
                continue
            finally:
                requests.release()
            notify(f"Imagen {index}/{count}: respuesta de IA recibida.")
            if cancel.is_set():
                raise ConversionCancelled("Análisis automático cancelado.")
            if proposal.fiable and proposal.mermaid:
                notify(f"Imagen {index}/{count}: preparando y validando Mermaid.")
                try:
                    render_mermaid(proposal.mermaid)
                    if cancel.is_set():
                        raise ConversionCancelled("Análisis automático cancelado.")
                    accept_diagram(
                        markdown, reference, proposal.mermaid, settings.ai.model, pending=True
                    )
                except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                    notify(f"Imagen {index}/{count}: no se pudo validar o guardar Mermaid.")
                    warnings.append(
                        f"Análisis automático de imagen {index}: "
                        "no se pudo validar o guardar la propuesta Mermaid."
                    )
                    retryable = True
                    continue
                notify(f"Imagen {index}/{count}: diagrama guardado pendiente de revisión.")
            else:
                notify(f"Imagen {index}/{count}: sin propuesta de diagrama fiable.")
            processed.add(index)
    finally:
        persist()
    return ConversionOutcome(markdown=markdown, warnings=tuple(warnings), retryable=retryable)
