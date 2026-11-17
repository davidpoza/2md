import os
import subprocess
import sys

import anyio
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.server.mcpserver.exceptions import ToolError
from PySide6.QtWidgets import QMessageBox

from twomd.config import MCPSettings, Settings, save_settings
from twomd.conversion import ConversionOutcome
from twomd.mcp_server import _document_path, leer_documento
from twomd.ui.settings_dialog import SettingsDialog


def test_mcp_settings_in_ui(qtbot, tmp_path):
    dialog = SettingsDialog(Settings(), None)
    qtbot.addWidget(dialog)
    assert not dialog.mcp_enabled.isChecked()
    dialog.mcp_enabled.setChecked(True)
    dialog.mcp_directory.setText(str(tmp_path))
    settings = dialog.values()
    assert settings.mcp.enabled
    assert settings.mcp.working_directory == str(tmp_path)


def test_mcp_settings_reject_nonexistent_directory(qtbot, tmp_path, monkeypatch):
    dialog = SettingsDialog(Settings(), None)
    qtbot.addWidget(dialog)
    dialog.mcp_enabled.setChecked(True)
    dialog.mcp_directory.setText(str(tmp_path / "inexistente"))
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    dialog.accept()
    assert messages
    assert dialog.result() != dialog.DialogCode.Accepted


def test_mcp_rejects_paths_outside_allowed_directory(tmp_path):
    allowed = tmp_path / "permitido"
    allowed.mkdir()
    inside = allowed / "archivo.pdf"
    inside.touch()
    outside = tmp_path / "fuera.pdf"
    outside.touch()
    assert _document_path("archivo.pdf", str(allowed)) == inside.resolve()
    with pytest.raises(PermissionError):
        _document_path(str(outside), str(allowed))
    with pytest.raises(PermissionError):
        _document_path("..\\fuera.pdf", str(allowed))


def test_mcp_rejects_symlink_outside_allowed_directory(tmp_path):
    allowed = tmp_path / "permitido"
    allowed.mkdir()
    outside_dir = tmp_path / "externo"
    outside_dir.mkdir()
    outside = outside_dir / "fuera.pdf"
    outside.touch()
    link = allowed / "enlace"
    try:
        link.symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            pytest.skip("El sistema no permite crear enlaces simbólicos.")
        environment = os.environ.copy()
        environment.update(TWOMD_LINK=str(link), TWOMD_TARGET=str(outside_dir))
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                (
                    "New-Item -ItemType Junction -Path $env:TWOMD_LINK "
                    "-Target $env:TWOMD_TARGET | Out-Null"
                ),
            ],
            env=environment,
            check=True,
            capture_output=True,
        )
    with pytest.raises(PermissionError):
        _document_path(str(link / outside.name), str(allowed))


def test_mcp_reads_document_to_configured_output(tmp_path, monkeypatch):
    from twomd import mcp_server

    allowed = tmp_path / "permitido"
    allowed.mkdir()
    source = allowed / "archivo.docx"
    source.touch()
    output = tmp_path / "salida"
    output.mkdir()
    markdown = output / "archivo.md"
    markdown.write_text("# Documento", encoding="utf-8")
    config = tmp_path / "settings.json"
    settings = Settings(
        output_directory=str(output),
        mcp=MCPSettings(enabled=True, working_directory=str(allowed)),
    )
    save_settings(config, settings)
    monkeypatch.setattr(mcp_server, "settings_path", lambda: config)
    calls = []

    def convert(source, destination, models_directory):
        calls.append((source, destination))
        return ConversionOutcome(markdown, ("Advertencia",))

    monkeypatch.setattr(mcp_server, "convert_document", convert)
    assert leer_documento("archivo.docx") == {
        "markdown": "# Documento",
        "archivo_markdown": str(markdown),
        "advertencias": ["Advertencia"],
    }
    assert calls == [(source.resolve(), output)]

    async def verify_tool_result():
        async with Client(mcp_server.server) as client:
            result = await client.call_tool("leer_documento", {"ruta": "archivo.docx"})
            assert not result.is_error
            assert result.structured_content["markdown"] == "# Documento"
            assert result.structured_content["archivo_markdown"] == str(markdown)

    anyio.run(verify_tool_result)
    save_settings(config, Settings(output_directory=str(output)))
    with pytest.raises(ToolError, match="desactivado"):
        leer_documento("archivo.docx")


def test_mcp_stdio_protocol_and_live_disable(tmp_path):
    appdata = tmp_path / "appdata"
    allowed = tmp_path / "permitido"
    allowed.mkdir()
    output = tmp_path / "salida"
    output.mkdir()
    outside = tmp_path / "fuera.pdf"
    outside.touch()
    config = appdata / "2MD" / "settings.json"
    settings = Settings(
        output_directory=str(output),
        mcp=MCPSettings(enabled=True, working_directory=str(allowed)),
    )
    save_settings(config, settings)
    environment = os.environ.copy()
    environment["APPDATA"] = str(appdata)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "twomd.mcp_server"],
        env=environment,
    )

    async def verify():
        async with Client(parameters) as client:
            tools = await client.list_tools()
            assert [tool.name for tool in tools.tools] == ["leer_documento"]
            rejected = await client.call_tool("leer_documento", {"ruta": str(outside)})
            assert rejected.is_error
            save_settings(config, Settings(output_directory=str(output)))
            disabled = await client.call_tool("leer_documento", {"ruta": "archivo.pdf"})
            assert disabled.is_error
            assert "desactivado" in disabled.content[0].text

    anyio.run(verify)
