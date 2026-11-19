# 2MD

Aplicación para Windows y Linux que convierte PDF y DOCX a Markdown, con revisión de
diagramas Mermaid y servidor MCP local. Implementada con Node.js, Electron,
`@xberg-io/xberg` y `mermaid`. La información funcional está en
[`docs/logic.md`](docs/logic.md) y la de seguridad en
[`docs/security.md`](docs/security.md).

## Compilar en Windows

Requiere Windows x64, Node.js 22.19 o posterior y npm. Desde la raíz del proyecto:

```powershell
.\scripts\build.ps1
```

Genera **`dist-node\2MD\2MD.exe`**. Para distribuir la aplicación copia la carpeta
`2MD` completa, incluidos sus recursos y DLL.
El script instala las dependencias fijadas en `package-lock.json`.

Para compilar MCP por separado (utiliza Windows PowerShell para su lanzador):

```powershell
.\scripts\build.ps1 -Mcp
```

Genera **`dist-node-mcp\2MD\2MD-MCP.exe`**; para MCP copia la carpeta `2MD` completa.

No se sobrescriben salidas existentes. Para repetir el empaquetado, elige una
carpeta nueva; `-OutputDirectory` se puede combinar con `-Mcp`:

```powershell
.\scripts\build.ps1 -OutputDirectory .\dist-node-nueva
```

## Compilar en Linux

Requiere Linux x64 (glibc), Node.js 22.19 o posterior y npm. Desde la raíz del
proyecto:

```sh
./scripts/build.sh
```

Genera **`dist-linux/2MD/2MD`**. Para distribuir la aplicación copia la carpeta
`2MD` completa. Para compilar MCP por separado:

```sh
./scripts/build.sh --mcp
```

Genera **`dist-linux-mcp/2MD/2MD-MCP`**, un lanzador de shell que se usa como
`command` en los clientes MCP. Tampoco se sobrescriben salidas existentes;
`--output DIRECTORIO` elige otra carpeta y se puede combinar con `--mcp`.

Las credenciales se guardan en el almacén Secret Service (GNOME Keyring, KWallet…),
que debe estar disponible en la sesión. Si la distribución restringe los espacios
de nombres sin privilegios (p. ej. AppArmor en Ubuntu 24.04) y Electron no arranca
por el sandbox, configura `chrome-sandbox` como `root` con permisos `4755`.
