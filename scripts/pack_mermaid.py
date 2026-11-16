"""Agrupa el runtime Mermaid para evitar que PyInstaller clasifique cada archivo."""

import os
import sys
import tempfile
import time
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile


def pack_mermaid(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    files = 0
    total_bytes = 0
    last_progress = time.monotonic()
    print("Agrupando recursos Mermaid; esta operacion puede tardar.", flush=True)
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as file:
            temporary = Path(file.name)
        with ZipFile(temporary, "w", compression=ZIP_STORED, allowZip64=True) as archive:

            def add_file(path: Path) -> None:
                nonlocal files, total_bytes, last_progress
                name = path.relative_to(source).as_posix()
                archive.write(path, name)
                files += 1
                total_bytes += archive.getinfo(name).file_size
                now = time.monotonic()
                if now - last_progress >= 5:
                    print(
                        f"Mermaid: {files} archivos, {total_bytes // (1024 * 1024)} MiB.",
                        flush=True,
                    )
                    last_progress = now

            for entry in ("render.mjs", "node_modules", "runtime", "browser"):
                path = source / entry
                if path.is_file():
                    add_file(path)
                elif path.is_dir():
                    for directory, subdirectories, names in os.walk(path):
                        subdirectories.sort()
                        for name in sorted(names):
                            file = Path(directory) / name
                            if entry == "node_modules" and file.suffix.lower() == ".map":
                                continue
                            add_file(file)
                else:
                    raise FileNotFoundError(f"Falta el recurso Mermaid: {entry}")
        os.replace(temporary, destination)
        print(
            f"Recursos Mermaid preparados: {files} archivos, {total_bytes // (1024 * 1024)} MiB.",
            flush=True,
        )
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    pack_mermaid(Path(sys.argv[1]), Path(sys.argv[2]))
