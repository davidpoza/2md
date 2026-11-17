"""Validación Mermaid local mediante mermaidx en un proceso aislado."""

import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree


def render_mermaid(code: str, timeout: int = 180) -> bytes:
    if not code.strip() or len(code) > 100_000 or "```" in code:
        raise ValueError("El código Mermaid está vacío o no tiene un formato válido.")
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--render-mermaid"]
    else:
        command = [sys.executable, "-m", "twomd.mermaid_renderer"]
    with tempfile.TemporaryDirectory(prefix="2md-mermaid-") as directory:
        root = Path(directory)
        source = root / "diagram.mmd"
        result = root / "diagram.svg"
        source.write_text(code, encoding="utf-8")
        try:
            process = subprocess.run(
                [*command, str(source), str(result)],
                capture_output=True,
                timeout=timeout,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("La validación Mermaid superó el tiempo de espera.") from error
        if process.returncode == 2:
            raise RuntimeError("Faltan dependencias del renderizador Mermaid local.")
        if process.returncode != 0 or not result.is_file():
            raise ValueError("No se pudo validar o renderizar el diagrama Mermaid.")
        data = result.read_bytes()
        try:
            svg = ElementTree.fromstring(data)
        except ElementTree.ParseError as error:
            raise ValueError("El renderizador Mermaid no produjo un SVG válido.") from error
        if svg.tag != "{http://www.w3.org/2000/svg}svg":
            raise ValueError("El renderizador Mermaid no produjo un SVG válido.")
        if any(element.tag.rsplit("}", 1)[-1] == "foreignObject" for element in svg.iter()):
            raise ValueError(
                "El diagrama contiene etiquetas HTML no compatibles con la vista SVG. "
                "Utiliza etiquetas Mermaid de texto."
            )
        return data
