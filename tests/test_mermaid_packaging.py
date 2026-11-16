from zipfile import ZipFile

import pytest

from scripts.pack_mermaid import pack_mermaid
from twomd import mermaid


def test_pack_and_extract_mermaid_resources(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source"
    for path in (
        "render.mjs",
        "node_modules/package/index.js",
        "runtime/node.exe",
        "browser/chrome/chrome-headless-shell.exe",
    ):
        target = source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.encode())
    source_map = source / "node_modules" / "package" / "index.js.map"
    source_map.write_text("source map", encoding="utf-8")
    archive = tmp_path / "runtime.zip"
    pack_mermaid(source, archive)
    assert "Recursos Mermaid preparados: 4 archivos" in capsys.readouterr().out
    with ZipFile(archive) as bundle:
        assert "node_modules/package/index.js.map" not in bundle.namelist()

    monkeypatch.setattr(mermaid, "_extracted_resources", None)
    extracted = mermaid._unpack_resources(archive)
    assert (extracted / "node_modules" / "package" / "index.js").read_bytes() == (
        b"node_modules/package/index.js"
    )
    assert mermaid._unpack_resources(archive) == extracted
    mermaid._extracted_resources.cleanup()


@pytest.mark.parametrize("name", ["../outside", "/absolute", "C:/outside", "a\\..\\outside"])
def test_unpack_rejects_unsafe_paths(tmp_path, monkeypatch, name):
    archive = tmp_path / "runtime.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr(name, "data")
    monkeypatch.setattr(mermaid, "_extracted_resources", None)
    with pytest.raises(ValueError):
        mermaid._unpack_resources(archive)
    assert not (tmp_path / "outside").exists()
