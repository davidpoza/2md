import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Empaquetado exclusivo de Windows")


@pytest.fixture
def build_project(tmp_path):
    root = tmp_path / "project"
    script = root / "scripts" / "build.ps1"
    script.parent.mkdir(parents=True)
    shutil.copy(Path(__file__).resolve().parents[1] / "scripts" / "build.ps1", script)
    for name in (
        "resources/models/docling-project--docling-layout-heron/model.safetensors",
        "resources/models/docling-project--docling-layout-heron/config.json",
        "resources/models/docling-project--docling-layout-heron/preprocessor_config.json",
        "resources/models/docling-project--docling-layout-heron/README.md",
        "resources/models/docling-project--docling-models/README.md",
        "resources/models/docling-project--docling-models/model_artifacts/tableformer/accurate/tm_config.json",
        "resources/models/docling-project--docling-models/model_artifacts/tableformer/accurate/tableformer_accurate.safetensors",
        "tools/mermaid/render.mjs",
        "tools/mermaid/runtime/node.exe",
        "tools/mermaid/node_modules/@mermaid-js/mermaid-cli/package.json",
        "tools/mermaid/browser/chrome-headless-shell.exe",
        "build/mermaid-runtime.zip",
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return root


def _run_build(root, format_name):
    log = root / "calls.jsonl"
    environment = os.environ.copy()
    environment.update(
        TWOMD_TEST_LOG=str(log),
        TWOMD_TEST_SCRIPT=str(root / "scripts" / "build.ps1"),
        TWOMD_TEST_OUTPUT=str(root / "output"),
        TWOMD_TEST_FORMAT=format_name,
    )
    command = (
        "function uv { ConvertTo-Json -InputObject @($args) -Compress | "
        "Add-Content -LiteralPath $env:TWOMD_TEST_LOG -Encoding UTF8; "
        "$global:LASTEXITCODE = 0 }; "
        "& $env:TWOMD_TEST_SCRIPT -Format $env:TWOMD_TEST_FORMAT "
        "-ReuseMermaid -OutputDirectory $env:TWOMD_TEST_OUTPUT"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    calls = (
        [json.loads(line) for line in log.read_text(encoding="utf-8-sig").splitlines()]
        if log.exists()
        else []
    )
    return result, calls


@pytest.mark.parametrize(
    ("format_name", "expected"),
    [
        ("Both", ["--onedir", "--onefile"]),
        ("OneDir", ["--onedir"]),
        ("OneFile", ["--onefile"]),
    ],
)
def test_build_formats_and_selected_models(build_project, format_name, expected):
    result, calls = _run_build(build_project, format_name)
    assert result.returncode == 0, result.stderr
    assert len(calls) == len(expected)
    for call, mode in zip(calls, expected, strict=True):
        call = [str(argument) for argument in call]
        assert mode in call
        assert not any(
            "heron-onnx" in argument or "tableformer\\fast" in argument for argument in call
        )
        assert any("tableformer\\accurate" in argument for argument in call)
        assert str(build_project / "output") in call


def test_missing_reused_archive_fails(build_project):
    (build_project / "build" / "mermaid-runtime.zip").unlink()
    result, calls = _run_build(build_project, "Both")
    assert result.returncode != 0
    assert not calls
