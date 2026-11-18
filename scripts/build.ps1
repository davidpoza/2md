param(
    [string]$OutputDirectory = "",
    [switch]$Mcp
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) {
    $folder = if ($Mcp) { "dist-node-mcp" } else { "dist-node" }
    $OutputDirectory = Join-Path $root $folder
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Se necesita Node.js 22.19 o posterior y npm."
}
Write-Warning "Empaquetado sin verificar funcionalmente: comprueba la distribucion en Windows limpio."
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
    $task = if ($Mcp) { "dist:mcp" } else { "dist" }
    & npm run $task -- "--config.directories.output=$OutputDirectory"
    if ($LASTEXITCODE -ne 0) {
        throw "electron-builder termino con el codigo $LASTEXITCODE."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $unpacked "2MD.exe") -PathType Leaf)) {
        throw "No se ha generado el runtime de la aplicacion."
    }
    if ($Mcp -and -not (Test-Path -LiteralPath (Join-Path $unpacked "2MD-MCP.exe") -PathType Leaf)) {
        throw "No se ha generado el lanzador MCP."
    }
    Move-Item -LiteralPath $unpacked -Destination $portable
    if ($Mcp) {
        Write-Host "MCP generado en $portable. Copia la carpeta completa."
    }
    else {
        Write-Host "Aplicacion portable generada en $portable. Ejecuta 2MD.exe y copia la carpeta completa."
    }
}
finally {
    Pop-Location
}
