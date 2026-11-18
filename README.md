# 2MD

Aplicación Windows para convertir PDF y DOCX a Markdown, con revisión de
diagramas Mermaid y servidor MCP local. Implementada con Node.js, Electron,
`@xberg-io/xberg` y `mermaid`. La información funcional está en
[`docs/logic.md`](docs/logic.md).

## Compilar

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
