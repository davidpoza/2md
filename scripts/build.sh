#!/bin/sh
# Uso: scripts/build.sh [--mcp] [--output DIRECTORIO]
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
mcp=0
output=""
while [ $# -gt 0 ]; do
    case "$1" in
        --mcp) mcp=1 ;;
        --output) [ $# -ge 2 ] || { echo "Falta el directorio de --output." >&2; exit 1; }; output=$2; shift ;;
        *) echo "Argumento desconocido: $1" >&2; exit 1 ;;
    esac
    shift
done
if [ -z "$output" ]; then
    if [ $mcp -eq 1 ]; then output="$root/dist-linux-mcp"; else output="$root/dist-linux"; fi
fi
mkdir -p "$output"
output=$(cd "$output" && pwd)
command -v npm >/dev/null 2>&1 || { echo "Se necesita Node.js 22.19 o posterior y npm." >&2; exit 1; }

portable="$output/2MD"
unpacked="$output/linux-unpacked"
if [ -e "$portable" ] || [ -e "$unpacked" ]; then
    echo "La salida ya existe. Elige un directorio de salida nuevo para no sobrescribirla." >&2
    exit 1
fi
echo "Aviso: empaquetado sin verificar funcionalmente: comprueba la distribucion en un Linux limpio." >&2
cd "$root"
npm ci --no-audit --no-fund || { echo "No se pudieron instalar las dependencias Node." >&2; exit 1; }
if [ $mcp -eq 1 ]; then task="dist:linux:mcp"; else task="dist:linux"; fi
npm run "$task" -- "--config.directories.output=$output" || { echo "electron-builder termino con error." >&2; exit 1; }
[ -f "$unpacked/2MD" ] || { echo "No se ha generado el runtime de la aplicacion." >&2; exit 1; }
if [ $mcp -eq 1 ] && [ ! -x "$unpacked/2MD-MCP" ]; then
    echo "No se ha generado el lanzador MCP." >&2
    exit 1
fi
mv "$unpacked" "$portable"
if [ $mcp -eq 1 ]; then
    echo "MCP generado en $portable. Copia la carpeta completa."
else
    echo "Aplicacion portable generada en $portable. Ejecuta ./2MD y copia la carpeta completa."
fi
