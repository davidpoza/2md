from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_delvewheel_libs_directory,
    copy_metadata,
)

root = Path(SPECPATH).parent
datas = copy_metadata("xberg")
binaries = []
hiddenimports = []
for package in (
    "xberg",
    "keyring",
    "win32ctypes",
    "mcp",
    "mcp_types",
    "mermaidx",
    "novasvg",
    "quickjs",
):
    package_datas, package_binaries, package_imports = collect_all(package)
    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_imports)
datas, binaries = collect_delvewheel_libs_directory("novasvg", datas=datas, binaries=binaries)

gui_script = root / "scripts" / "entrypoint.py"
mcp_script = root / "scripts" / "mcp_entrypoint.py"
analysis = Analysis(
    [str(gui_script), str(mcp_script)],
    pathex=[str(root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)


def scripts_for(script):
    main_scripts = {gui_script.resolve(), mcp_script.resolve()}
    shared = [item for item in analysis.scripts if Path(item[1]).resolve() not in main_scripts]
    selected = [item for item in analysis.scripts if Path(item[1]).resolve() == script.resolve()]
    if len(selected) != 1:
        raise RuntimeError(f"No se encontró el punto de entrada: {script.name}")
    return shared + selected


gui = EXE(
    pyz,
    scripts_for(gui_script),
    exclude_binaries=True,
    name="2MD",
    console=False,
    strip=False,
    upx=True,
)
mcp = EXE(
    pyz,
    scripts_for(mcp_script),
    exclude_binaries=True,
    name="2MD-MCP",
    console=True,
    strip=False,
    upx=True,
)
bundle = COLLECT(gui, mcp, analysis.binaries, analysis.datas, name="2MD", strip=False, upx=True)
