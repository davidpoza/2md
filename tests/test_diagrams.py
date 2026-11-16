import json
from threading import BoundedSemaphore, Event

import httpx
import pytest
from PIL import Image

from twomd.cache import output_hashes
from twomd.config import AISettings, NetworkSettings, Settings
from twomd.conversion import ConversionCancelled, ConversionOutcome
from twomd.diagrams import DiagramProposal, propose_diagram


def test_proposal_sends_image_and_context_only_when_enabled(tmp_path, monkeypatch):
    from twomd import diagrams

    image = tmp_path / "imagen.png"
    Image.new("RGB", (2, 2), "white").save(image)
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        body = {"categoria": "flujo", "fiable": True, "mermaid": "flowchart LR\n A-->B"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}}]})

    monkeypatch.setattr(
        diagrams,
        "create_http_client",
        lambda settings, password: httpx.Client(transport=httpx.MockTransport(respond)),
    )
    settings = AISettings(enabled=True, base_url="https://example.com/v1", model="vision")
    proposal = propose_diagram(image, "contexto", settings, NetworkSettings(), "clave", None)
    assert proposal.fiable
    content = requests[0]["messages"][1]["content"]
    assert "contexto" in content[0]["text"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    settings.enabled = False
    with pytest.raises(ValueError):
        propose_diagram(image, "contexto", settings, NetworkSettings(), "clave", None)
    assert len(requests) == 1


def test_rejects_invalid_mermaid_proposal(tmp_path, monkeypatch):
    from twomd import diagrams

    image = tmp_path / "imagen.png"
    Image.new("RGB", (2, 2), "white").save(image)
    body = {"categoria": "fotografia", "fiable": True, "mermaid": "flowchart LR\n A-->B"}
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(body)}}]}
        )
    )
    monkeypatch.setattr(
        diagrams, "create_http_client", lambda settings, password: httpx.Client(transport=transport)
    )
    settings = AISettings(enabled=True, base_url="https://example.com/v1", model="vision")
    with pytest.raises(ValueError, match="JSON válida"):
        propose_diagram(image, "", settings, NetworkSettings(), "clave", None)


def test_automatic_diagrams_insert_reviewable_results_and_report_failures(tmp_path, monkeypatch):
    from twomd import automatic_diagrams
    from twomd.review import accept_diagram, pending_diagram, picture_references

    assets = tmp_path / "assets"
    assets.mkdir()
    for name in ("diagram.png", "photo.png", "error.png"):
        Image.new("RGB", (4, 4), "white").save(assets / name)
    markdown = tmp_path / "documento.md"
    markdown.write_text(
        "\n".join(
            f"![{name}](assets/{name})" for name in ("diagram.png", "photo.png", "error.png")
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "conversion-report.json"
    report_path.write_text(
        json.dumps(
            {
                "diagramas": 0,
                "diagramas_convertidos": 0,
                "diagramas_pendientes_revision": 0,
                "advertencias": [],
                "estado": "completado",
            }
        ),
        encoding="utf-8",
    )
    calls = []
    failed_once = False

    def propose(image, context, ai, network, key, password):
        nonlocal failed_once
        calls.append(image.name)
        if image.name == "error.png" and not failed_once:
            failed_once = True
            raise RuntimeError("clave-secreta")
        if image.name in {"photo.png", "error.png"}:
            return DiagramProposal(categoria="fotografia", fiable=False)
        return DiagramProposal(categoria="flujo", fiable=True, mermaid="flowchart LR\nA-->B")

    monkeypatch.setattr(automatic_diagrams, "propose_diagram", propose)
    monkeypatch.setattr(automatic_diagrams, "render_mermaid", lambda code: b"PNG")
    settings = Settings(
        ai=AISettings(enabled=True, base_url="https://example.com/v1", model="vision")
    )
    result = automatic_diagrams.process_automatic_diagrams(
        ConversionOutcome(markdown, ()), settings, "clave", None, Event(), BoundedSemaphore(1)
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert calls == ["diagram.png", "photo.png", "error.png"]
    assert "![diagram.png](assets/diagram.png)" in markdown.read_text(encoding="utf-8")
    assert "Diagrama generado por IA: pendiente de revisión" in markdown.read_text(encoding="utf-8")
    assert pending_diagram(markdown, picture_references(markdown)[0]) == "flowchart LR\nA-->B"
    assert report["diagramas_pendientes_revision"] == 1
    assert report["imagenes_analizadas_ia"] == [1, 2]
    assert report["estado"] == "completado_con_advertencias"
    assert report["archivos"] == output_hashes(tmp_path, markdown)
    assert "clave-secreta" not in report_path.read_text(encoding="utf-8")
    assert result.warnings
    assert result.retryable

    calls.clear()
    retried = automatic_diagrams.process_automatic_diagrams(
        result, settings, "clave", None, Event(), BoundedSemaphore(1)
    )
    assert calls == ["error.png"]
    assert not retried.retryable
    assert not retried.warnings
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["estado"] == "completado"
    assert report["imagenes_analizadas_ia"] == [1, 2, 3]
    reference = picture_references(markdown)[0]
    accept_diagram(markdown, reference, "flowchart LR\nA-->C")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["diagramas_pendientes_revision"] == 0
    assert report["diagramas_convertidos"] == 1
    assert pending_diagram(markdown, picture_references(markdown)[0]) is None
    assert "flowchart LR\nA-->C" in markdown.read_text(encoding="utf-8")


def test_automatic_analysis_respects_cancellation(tmp_path):
    from twomd.automatic_diagrams import process_automatic_diagrams

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "image.png").write_bytes(b"image")
    markdown = tmp_path / "documento.md"
    markdown.write_text("![imagen](assets/image.png)", encoding="utf-8")
    (tmp_path / "conversion-report.json").write_text(
        json.dumps({"advertencias": [], "estado": "completado"}), encoding="utf-8"
    )
    cancel = Event()
    cancel.set()
    with pytest.raises(ConversionCancelled):
        process_automatic_diagrams(
            ConversionOutcome(markdown, ()), Settings(), "clave", None, cancel, BoundedSemaphore(1)
        )
