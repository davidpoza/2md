"""Validación Mermaid en un proceso aislado con recursos locales."""

import subprocess
import sys
import tempfile
from pathlib import Path

import twomd


def render_mermaid(code: str, timeout: int = 180) -> bytes:
    if not code.strip() or len(code) > 100_000 or "```" in code:
        raise ValueError("El código Mermaid está vacío o no tiene un formato válido.")
    if getattr(sys, "frozen", False):
        resources = Path(twomd.__file__).parent / "resources" / "mermaid"
    else:
        resources = Path(__file__).resolve().parents[2] / "tools" / "mermaid"
    node = resources / "runtime" / "node.exe"
    script = resources / "render.mjs"
    browsers = sorted((resources / "browser").glob("**/chrome-headless-shell.exe"))
    if not node.is_file() or not script.is_file() or not browsers:
        raise RuntimeError("Faltan los recursos locales del validador Mermaid.")
    with tempfile.TemporaryDirectory(prefix="2md-mermaid-") as directory:
        root = Path(directory)
        source = root / "diagram.mmd"
        result = root / "diagram.png"
        source.write_text(code, encoding="utf-8")
        try:
            process = subprocess.run(
                [str(node), str(script), str(source), str(result), str(browsers[0])],
                capture_output=True,
                timeout=timeout,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("La validación Mermaid superó el tiempo de espera.") from error
        if process.returncode != 0 or not result.is_file():
            raise ValueError("No se pudo validar o renderizar el diagrama Mermaid.")
        data = result.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("El renderizador Mermaid no produjo una imagen PNG válida.")
        return data
