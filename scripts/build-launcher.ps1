param(
    [Parameter(Mandatory = $true)][string]$Destination
)

$ErrorActionPreference = "Stop"
$source = Join-Path $PSScriptRoot "McpLauncher.cs"
if (Test-Path -LiteralPath $Destination) {
    throw "El lanzador ya existe: $Destination"
}
Add-Type -Path $source -OutputAssembly $Destination -OutputType ConsoleApplication
