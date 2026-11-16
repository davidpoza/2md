"""Clasificación y generación opcional de diagramas pendientes de revisión."""

import json
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
            while not requests.acquire(timeout=0.2):
                if cancel.is_set():
                    raise ConversionCancelled("Análisis automático cancelado.")
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
                )
            except ConversionCancelled:
                raise
            except Exception as error:  # noqa: BLE001
                warnings.append(f"Análisis automático de imagen {index}: {safe_error(error)}")
                retryable = True
                continue
            finally:
                requests.release()
            if cancel.is_set():
                raise ConversionCancelled("Análisis automático cancelado.")
            if proposal.fiable and proposal.mermaid:
                try:
                    render_mermaid(proposal.mermaid)
                    if cancel.is_set():
                        raise ConversionCancelled("Análisis automático cancelado.")
                    accept_diagram(
                        markdown, reference, proposal.mermaid, settings.ai.model, pending=True
                    )
                except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                    warnings.append(
                        f"Análisis automático de imagen {index}: "
                        "no se pudo validar o guardar la propuesta Mermaid."
                    )
                    retryable = True
                    continue
            processed.add(index)
    finally:
        persist()
    return ConversionOutcome(markdown=markdown, warnings=tuple(warnings), retryable=retryable)
