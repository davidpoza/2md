$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$models = Join-Path $root "resources\models"
$mermaid = Join-Path $root "tools\mermaid"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "Se necesita uv para preparar la distribución de desarrollo."
}
if (-not (Test-Path -LiteralPath $models -PathType Container)) {
    throw "Faltan los modelos locales de Docling en resources\models. Consulta README.md."
}
foreach ($required in @(
    "docling-project--docling-layout-heron\model.safetensors",
    "docling-project--docling-models\model_artifacts\tableformer"
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $models $required))) {
        throw "Falta un recurso de Docling: $required."
    }
}
foreach ($required in @("render.mjs", "runtime\node.exe", "node_modules\@mermaid-js\mermaid-cli\package.json")) {
    if (-not (Test-Path -LiteralPath (Join-Path $mermaid $required) -PathType Leaf)) {
        throw "Falta un recurso de Mermaid: $required."
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $mermaid "browser") -PathType Container) -or
    -not (Get-ChildItem -LiteralPath (Join-Path $mermaid "browser") -Filter "chrome-headless-shell.exe" -File -Recurse | Select-Object -First 1)) {
    throw "Falta Chromium para Mermaid."
}

Write-Warning "Distribución sin verificar: prueba el EXE y sus recursos en Windows limpio."
Push-Location $root
try {
    & uv run --python 3.12 --group package pyinstaller `
        --noconfirm --windowed --onefile --name 2MD `
        --paths src `
        --collect-all docling `
        --collect-all docling_core `
        --collect-all docling_parse `
        --collect-all docling_ibm_models `
        --copy-metadata torch `
        --collect-all keyring `
        --collect-all win32ctypes `
        --add-data "$models;twomd\resources\models" `
        --add-data "$mermaid;twomd\resources\mermaid" `
        scripts\entrypoint.py
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller terminó con el código $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
