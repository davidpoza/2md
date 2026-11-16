import json

import httpx
import pytest
from PIL import Image

from twomd.config import AISettings, NetworkSettings
from twomd.diagrams import propose_diagram


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
