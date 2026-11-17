import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree

import pytest

from twomd.mermaid import render_mermaid


@pytest.mark.parametrize(
    "code",
    [
        "flowchart LR\n A --> B",
        "stateDiagram-v2\n [*] --> Activo\n Activo --> [*]",
        "sequenceDiagram\n Alice->>Bob: Hola",
        "erDiagram\n CLIENTE ||--o{ PEDIDO : realiza",
        "mindmap\n root((Proyecto))\n  Requisitos\n  Desarrollo",
        "flowchart TD\n Director --> Equipo",
        "architecture-beta\n service api(server)[API]\n service db(database)[BD]\n api:R -- L:db",
    ],
)
def test_real_mermaid_renders_vector_diagrams(code):
    svg = ElementTree.fromstring(render_mermaid(code))
    assert svg.tag == "{http://www.w3.org/2000/svg}svg"
    assert not list(svg.iter("{http://www.w3.org/2000/svg}foreignObject"))


def test_real_mermaid_rejects_invalid_syntax():
    with pytest.raises(ValueError):
        render_mermaid("flowchart LR\n A -->")


def test_mermaid_does_not_fetch_image_urls():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(204)
            self.end_headers()

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/imagen.png"
        diagram = (
            '%%{init: {"securityLevel":"loose"}}%%\n'
            f"flowchart LR\nA[\"<img src='{url}'/>\"] --> B"
        )
        try:
            render_mermaid(diagram)
        except ValueError:
            pass
        assert requests == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_mermaid_timeout_is_reported(monkeypatch):
    from twomd import mermaid

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(mermaid.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="tiempo de espera"):
        render_mermaid("flowchart LR\nA-->B", timeout=1)


def test_frozen_renderer_uses_executable_without_browser(monkeypatch):
    from twomd import mermaid

    calls = []

    def run(command, **kwargs):
        calls.append(command)
        Path(command[-1]).write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(mermaid.sys, "frozen", True, raising=False)
    monkeypatch.setattr(mermaid.subprocess, "run", run)
    render_mermaid("flowchart LR\nA-->B")
    assert calls[0][:2] == [mermaid.sys.executable, "--render-mermaid"]


@pytest.mark.parametrize(
    "content",
    [
        b"not SVG",
        b'<html xmlns="http://www.w3.org/1999/xhtml"/>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
    ],
)
def test_renderer_rejects_invalid_or_unsupported_svg(monkeypatch, content):
    from twomd import mermaid

    def run(command, **kwargs):
        Path(command[-1]).write_bytes(content)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(mermaid.subprocess, "run", run)
    with pytest.raises(ValueError):
        render_mermaid("flowchart LR\nA-->B")
