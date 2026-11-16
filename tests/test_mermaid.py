import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from twomd.mermaid import render_mermaid

_RESOURCES = Path(__file__).resolve().parents[1] / "tools" / "mermaid"
pytestmark = pytest.mark.skipif(
    not (_RESOURCES / "runtime" / "node.exe").is_file()
    or not list((_RESOURCES / "browser").glob("**/chrome-headless-shell.exe"))
    or not (_RESOURCES / "node_modules" / "@mermaid-js" / "mermaid-cli").is_dir(),
    reason="Recursos locales de Mermaid no instalados",
)


def test_real_mermaid_render_and_invalid_syntax():
    assert render_mermaid("flowchart LR\n A --> B").startswith(b"\x89PNG\r\n\x1a\n")
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
