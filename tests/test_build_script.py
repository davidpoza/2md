import json
import os
import runpy
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
    return root


def _run_build(root):
    log = root / "calls.jsonl"
    environment = os.environ.copy()
    environment.update(
        TWOMD_TEST_LOG=str(log),
        TWOMD_TEST_SCRIPT=str(root / "scripts" / "build.ps1"),
        TWOMD_TEST_OUTPUT=str(root / "output"),
    )
    command = (
        "function uv { ConvertTo-Json -InputObject @($args) -Compress | "
        "Add-Content -LiteralPath $env:TWOMD_TEST_LOG -Encoding UTF8; "
        "$global:LASTEXITCODE = 0 }; "
        "& $env:TWOMD_TEST_SCRIPT -OutputDirectory $env:TWOMD_TEST_OUTPUT"
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


def test_build_only_uses_portable_spec(build_project):
    result, calls = _run_build(build_project)
    assert result.returncode == 0, result.stderr
    assert len(calls) == 1
    call = [str(argument) for argument in calls[0]]
    assert not any(argument in {"--onefile", "--onedir"} for argument in call)
    assert str(build_project / "scripts" / "portable.spec") in call
    assert str(build_project / "output") in call


def test_portable_spec_shares_resources_and_separates_entrypoints(build_project, monkeypatch):
    from PyInstaller.utils import hooks

    original = Path(__file__).resolve().parents[1] / "scripts" / "portable.spec"
    spec = build_project / "scripts" / "portable.spec"
    shutil.copy(original, spec)
    monkeypatch.setattr(hooks, "copy_metadata", lambda package: [])
    delvewheel = []

    def collect_dlls(package, *, datas, binaries):
        delvewheel.append(package)
        return datas, binaries

    monkeypatch.setattr(hooks, "collect_delvewheel_libs_directory", collect_dlls)
    gui = build_project / "scripts" / "entrypoint.py"
    mcp = build_project / "scripts" / "mcp_entrypoint.py"
    calls = []
    collected = []

    def collect(package):
        collected.append(package)
        return [], [], []

    monkeypatch.setattr(hooks, "collect_all", collect)

    class FakeAnalysis:
        def __init__(self, scripts, **kwargs):
            assert scripts == [str(gui), str(mcp)]
            self.scripts = [
                ("hook", str(build_project / "hook.py"), "PYSOURCE"),
                ("gui", str(gui), "PYSOURCE"),
                ("mcp", str(mcp), "PYSOURCE"),
            ]
            self.pure = []
            self.binaries = []
            self.datas = kwargs["datas"]

    def exe(pyz, scripts, **kwargs):
        calls.append((pyz, scripts, kwargs))
        return kwargs["name"]

    shared_pyz = object()
    result = runpy.run_path(
        str(spec),
        init_globals={
            "SPECPATH": str(spec.parent),
            "Analysis": FakeAnalysis,
            "PYZ": lambda pure: shared_pyz,
            "EXE": exe,
            "COLLECT": lambda *args, **kwargs: (args, kwargs),
        },
    )
    assert len(calls) == 2
    assert calls[0][0] is calls[1][0] is shared_pyz
    assert calls[0][2]["console"] is False
    assert calls[1][2]["console"] is True
    assert [item[0] for item in calls[0][1]] == ["hook", "gui"]
    assert [item[0] for item in calls[1][1]] == ["hook", "mcp"]
    assert result["bundle"][0][:2] == ("2MD", "2MD-MCP")
    assert {"xberg", "mermaidx", "novasvg", "quickjs"} <= set(collected)
    assert delvewheel == ["novasvg"]
    sources = [entry[0] for entry in result["analysis"].datas]
    assert not any("mermaid-runtime" in source for source in sources)
    assert not any("docling" in source.lower() for source in sources)
