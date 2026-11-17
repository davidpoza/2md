param(
    [switch]$ReuseMermaid,
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$models = Join-Path $root "resources\models"
$mermaid = Join-Path $root "tools\mermaid"
$mermaidArchive = Join-Path $root "build\mermaid-runtime.zip"
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $root "dist"
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "Se necesita uv para preparar la distribucion de desarrollo."
}
if (-not (Test-Path -LiteralPath $models -PathType Container)) {
    throw "Faltan los modelos locales de Docling en resources\models. Consulta README.md."
}
foreach ($required in @(
    "docling-project--docling-layout-heron\model.safetensors",
    "docling-project--docling-layout-heron\config.json",
    "docling-project--docling-layout-heron\preprocessor_config.json",
    "docling-project--docling-layout-heron\README.md",
    "docling-project--docling-models\README.md",
    "docling-project--docling-models\model_artifacts\tableformer\accurate\tm_config.json",
    "docling-project--docling-models\model_artifacts\tableformer\accurate\tableformer_accurate.safetensors"
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $models $required) -PathType Leaf)) {
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

Write-Warning "Distribucion sin verificar: prueba el EXE y sus recursos en Windows limpio."
Push-Location $root
try {
    if ($ReuseMermaid) {
        if (-not (Test-Path -LiteralPath $mermaidArchive -PathType Leaf)) {
            throw "No existe el archivo Mermaid para reutilizar."
        }
        Write-Warning "Se reutiliza Mermaid. No uses -ReuseMermaid si han cambiado sus recursos."
    }
    else {
        & uv run --python 3.12 --group package python scripts\pack_mermaid.py $mermaid $mermaidArchive
        if ($LASTEXITCODE -ne 0) {
            throw "No se pudieron agrupar los recursos de Mermaid."
        }
    }
    $arguments = @(
        "--noconfirm",
        "--workpath", (Join-Path $root "build\pyinstaller"),
        "--distpath", $OutputDirectory,
        (Join-Path $root "scripts\portable.spec")
    )
    Write-Host "Iniciando PyInstaller para la carpeta portable..."
    & uv run --python 3.12 --group package pyinstaller @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller termino con el codigo $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
