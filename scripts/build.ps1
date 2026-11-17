param(
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $root "dist-node"
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Se necesita Node.js 22.19 o posterior y npm."
}
Write-Warning "Distribucion sin verificar: prueba el EXE y sus recursos en Windows limpio."
Push-Location $root
try {
    $portable = Join-Path $OutputDirectory "2MD"
    $unpacked = Join-Path $OutputDirectory "win-unpacked"
    if ((Test-Path -LiteralPath $portable) -or (Test-Path -LiteralPath $unpacked)) {
        throw "La salida ya existe. Elige un OutputDirectory nuevo para no sobrescribirla."
    }
    & npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudieron instalar las dependencias Node."
    }
    & npm run dist -- "--config.directories.output=$OutputDirectory"
    if ($LASTEXITCODE -ne 0) {
        throw "electron-builder termino con el codigo $LASTEXITCODE."
    }
    Move-Item -LiteralPath $unpacked -Destination $portable
    Write-Host "Portable generado en $portable. Copia la carpeta completa."
}
finally {
    Pop-Location
}
