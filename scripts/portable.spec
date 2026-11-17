from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_delvewheel_libs_directory,
    copy_metadata,
)

root = Path(SPECPATH).parent
models = root / "resources" / "models"
layout = models / "docling-project--docling-layout-heron"
tables = models / "docling-project--docling-models"
layout_destination = r"twomd\resources\models\docling-project--docling-layout-heron"
table_destination = r"twomd\resources\models\docling-project--docling-models"

datas = []
for filename in (
    "config.json",
    "preprocessor_config.json",
    "model.safetensors",
    "README.md",
    "docling_heron_400.png",
):
    source = layout / filename
    if source.is_file():
        datas.append((str(source), layout_destination))
datas.extend(
    [
        (str(tables / "README.md"), table_destination),
        (
            str(tables / "model_artifacts" / "tableformer" / "accurate"),
            table_destination + r"\model_artifacts\tableformer\accurate",
        ),
    ]
)
datas.extend(copy_metadata("torch"))
datas.extend(collect_data_files("latex2mathml"))
datas.extend(copy_metadata("latex2mathml"))
binaries = []
hiddenimports = []
for package in (
    "docling",
    "docling_core",
    "docling_parse",
    "docling_ibm_models",
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
