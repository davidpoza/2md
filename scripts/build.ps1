param(
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$models = Join-Path $root "resources\models"
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
Write-Warning "Distribucion sin verificar: prueba el EXE y sus recursos en Windows limpio."
Push-Location $root
try {
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
