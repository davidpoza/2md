"""Punto de entrada mínimo para aislar QuickJS del proceso de la interfaz."""

import sys
from pathlib import Path


def main() -> int:
    try:
        import mermaidx
    except ImportError:
        return 2
    if len(sys.argv) != 3:
        return 2
    try:
        code = Path(sys.argv[1]).read_text(encoding="utf-8")
        if not code.strip() or len(code) > 100_000 or "```" in code:
            return 1
        svg = mermaidx.render(
            code,
            backend="js:mermaid",
            engine="quickjs",
            config={
                "securityLevel": "strict",
                "maxTextSize": 100_000,
                "htmlLabels": False,
                "flowchart": {"htmlLabels": False},
                "journey": {"textPlacement": "svg"},
                "timeline": {"textPlacement": "svg"},
            },
        ).svg()
        Path(sys.argv[2]).write_text(svg, encoding="utf-8")
    except Exception:  # noqa: BLE001
        print("No se pudo validar o renderizar el diagrama Mermaid.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
