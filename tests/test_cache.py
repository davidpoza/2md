import json

from twomd.cache import output_hashes, read_cached_result


def test_cache_refuses_modified_output(tmp_path):
    markdown = tmp_path / "doc.md"
    source = tmp_path / "doc.docx"
    markdown.write_text("original", encoding="utf-8")
    report = {
        "sha256": "source",
        "archivo_original": str(source),
        "version_xberg": "version",
        "configuracion_hash": "config",
        "version_cache": 2,
        "estado": "completado",
        "archivos": output_hashes(tmp_path, markdown),
        "markdown": markdown.name,
        "advertencias": [],
    }
    (tmp_path / "conversion-report.json").write_text(json.dumps(report), encoding="utf-8")
    assert read_cached_result(tmp_path, source, "source", "version", "config") is not None
    markdown.write_text("modificado", encoding="utf-8")
    assert read_cached_result(tmp_path, source, "source", "version", "config") is None
