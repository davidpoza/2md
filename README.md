# 2MD

Aplicación de escritorio para convertir documentos empresariales a Markdown.

## Implementación Node / Electron

La aplicación principal se ha reimplementado en **Node.js y Electron**, con
`@xberg-io/xberg` para extraer PDF/DOCX y la librería oficial `mermaid` para
validar y renderizar diagramas localmente. La lógica funcional vigente está en
[`docs/logic.md`](docs/logic.md).

La nueva implementación está en `app`. Conserva selección temporal de archivos,
carpetas sin recursión, arrastrar y soltar, deduplicación, destino configurable,
concurrencia, cancelación cooperativa y reintentos. Mantiene Markdown con imágenes
en `assets`, informes, comprobación de integridad para reutilizar resultados y
rechazo de salidas existentes no reutilizables. Los resultados Python anteriores
no se sobrescriben ni se reutilizan automáticamente: la versión del motor,
aplicación y configuración forma parte de la nueva identidad de salida.

La IA y MCP siguen desactivados por defecto. El análisis automático exige
consentimiento por lote; las propuestas fiables y válidas quedan pendientes de
revisión. La revisión manual permite editar, validar y comparar original y SVG
con zoom, antes de aceptar explícitamente. Editar invalida la validación. Mermaid
se ejecuta en una ventana aislada, sin Node ni acceso remoto, con un límite de
180 segundos. No se admiten HTML ni directivas que alteren la configuración.

Las preferencias conservan el esquema de `%APPDATA%\2MD\settings.json`.
Las credenciales se almacenan en Windows Credential Manager mediante
`@napi-rs/keyring`, con los destinos `2MD/api` y `2MD/proxy`; nunca en JSON.
La red admite acceso directo, proxy de sistema/entorno o manual con autenticación
Basic y exclusiones por host/IP. Se emplean certificados del sistema o el archivo
CA elegido, sin desactivar TLS. NTLM y Kerberos no están implementados.

### Desarrollo Node

Requiere Windows x64 y **Node.js 22.19 o posterior** (recomendado Node 24).

```powershell
npm ci
npm start
```

`npm start` abre la aplicación. `npm run mcp` inicia únicamente el servidor
stdio con Node; se debe activar MCP y configurar sus carpetas previamente.
No se descargan modelos OCR ni recursos Mermaid durante la conversión.

Las pruebas Node están en `tests-node`; se ejecutan con `npm test` en un entorno
autorizado. Esta migración no ha ejecutado tests, builds ni aplicaciones gráficas
en el entorno de trabajo: la revisión sintáctica no demuestra paridad funcional.
Es necesario verificar extracción con documentos representativos, renderizado,
almacén de credenciales, redes corporativas y los dos ejecutables en Windows limpio.

### Distribución portable Node

```powershell
.\scripts\build.ps1
# O selecciona una salida nueva:
.\scripts\build.ps1 -OutputDirectory dist-node-nueva
```

El script instala desde `package-lock.json` y empaqueta con electron-builder.
Genera `dist-node\2MD\2MD.exe` y `dist-node\2MD\2MD-MCP.exe`, con dependencias
compartidas. **Copia la carpeta completa**; no son ejecutables independientes
de sus recursos. No requiere Python, Qt ni Node instalado en el equipo destino.
No sobrescribe una distribución existente.

`2MD-MCP.exe` es un pequeño lanzador de consola generado con el compilador .NET
incluido en Windows PowerShell. Ejecuta el Node integrado en Electron y conecta
los tres streams sin añadir mensajes a stdout. La aplicación y la conversión
son JavaScript; el lanzador solo adapta el arranque stdio en Windows.
El portable aún no ha sido generado ni verificado.

### MCP Node: documentos e imágenes

Activa MCP en **Configuración**, selecciona el directorio permitido y un destino.
El cliente inicia `2MD-MCP.exe` por stdio:

```json
{
  "mcpServers": {
    "2md": {
      "command": "C:\\ruta\\2MD\\2MD-MCP.exe",
      "timeout": 600
    }
  }
}
```

`leer_documento` recibe `ruta`, relativa al directorio permitido o absoluta
dentro de él. Resuelve rutas reales para rechazar escapes por `..`, enlaces o
directorios hermanos. Lee la configuración vigente en cada operación.
Devuelve `markdown`, `archivo_markdown`, `advertencias` e `imagenes`.
El Markdown devuelto referencia imágenes mediante URI `2md://images/...`.
Las imágenes también se anuncian como `resource_link` y se obtienen mediante
`resources/read`, como contenido binario base64 con su MIME. No se limita a
devolver rutas que el cliente no puede abrir. Los recursos pertenecen a la sesión
stdio actual y se revocan si dejan de estar autorizados o cambia su integridad.
El Markdown guardado en disco mantiene sus enlaces relativos a `assets`.

El cliente debe soportar recursos MCP para leer las imágenes. Leer un recurso
no concede permiso para enviarlo a un servicio remoto de IA. MCP nunca ejecuta
IA ni OCR y se ejecuta con los permisos del usuario, no en un aislamiento del SO.

## Implementación Python anterior (referencia histórica)

Las secciones siguientes describen la versión anterior conservada en `src` y
`tests`, no los comandos ni las dependencias de la aplicación Node vigente.
El script `scripts\build.ps1` ahora empaqueta Node, no Python.

### Estado anterior: implementación parcial

La ventana permite seleccionar archivos DOCX y PDF, añadir los archivos de una carpeta
sin recorrer subcarpetas, arrastrarlos y elegir una carpeta de destino. La selección
es temporal; el destino y el límite de concurrencia se guardan en
`%APPDATA%\2MD\settings.json`. Este archivo no almacena credenciales.

Se han implementado la conversión local por lotes mediante Xberg, workers con
concurrencia configurable, cancelación cooperativa y reintentos, exportación Markdown
con imágenes referenciadas, informes de conversiones completadas y reutilización
de resultados cuyo contenido y configuración no han cambiado. No se sobrescriben
carpetas existentes que no se puedan reutilizar. Una exportación fallida puede dejar
una carpeta incompleta; los errores no producen todavía un informe individual.

La extracción utiliza Xberg sin OCR para evitar descargas de modelos y conservar
el comportamiento actual: el texto de imágenes y páginas escaneadas no se extrae,
y cada PDF genera una advertencia. Las imágenes detectadas se guardan como archivos
referenciados en `assets`. La cancelación espera a que termine la operación Xberg
en curso.

La interfaz contiene configuración de IA, proxy y CA, almacenamiento de secretos
con el backend de Windows de keyring y pruebas explícitas de conexión y visión.
La revisión de imágenes de un documento convertido permite solicitar una propuesta
de IA con consentimiento, editarla y validarla antes de aceptarla. El Markdown
conserva la imagen original junto al bloque Mermaid aceptado. La casilla de la
ventana principal permite analizar automáticamente las imágenes con el modelo
configurado, previo consentimiento para enviar imágenes y contexto. Los diagramas
detectados y validados se insertan junto a la imagen y se marcan como pendientes
de revisión; los errores se muestran y pueden reintentarse. Se han probado localmente el
renderizado Mermaid, el rechazo de sintaxis inválida y el bloqueo de una petición
de imagen a localhost. El ejecutable sigue sin verificarse, y tampoco se ha probado
la aplicación con una red corporativa.

## Desarrollo

Se ha elegido Python 3.12 x64 como base inicial. En Windows se puede seleccionar con
el lanzador `py`; este proyecto fija la versión en `.python-version` para uv.
Con uv instalado:

```powershell
py -3.12 --version
uv sync --python 3.12
uv run 2md
```

Los tests se encuentran en `tests`; la configuración de calidad usa pytest,
pytest-qt y Ruff. Xberg está fijado a la versión 1.3.8, que publica un wheel
Windows x64 en su índice de archivo; `pyproject.toml` configura ese índice para uv.
`uv.lock` fija las dependencias resueltas; la distribución todavía no está verificada.

### Empaquetado de desarrollo

`scripts\build.ps1` genera únicamente la carpeta portable `dist\2MD`, con
`2MD.exe` y `2MD-MCP.exe`. Ambos comparten sus dependencias y la carpeta debe
copiarse completa. El script no elimina un `dist\2MD.exe` antiguo que ya exista.

```powershell
.\scripts\build.ps1
```

El renderizador Mermaid usa `mermaidx` con QuickJS, sin Node, npm, Puppeteer ni
Chromium. Ya no se utiliza el parámetro `-ReuseMermaid` ni se genera un ZIP de runtime.

Requiere uv y Python 3.12 x64. No requiere modelos de extracción ni descargas
durante la conversión. Las dependencias Python del renderizador, sus
archivos JavaScript y fuentes se incorporan mediante PyInstaller; no se extrae
un navegador al validar un diagrama. El guion **no se ha validado** y no constituye
una distribución final. Se deben comprobar también las licencias y el funcionamiento
sin conexión en Windows limpio.

`uv sync` instala también el renderizador de desarrollo. `mermaidx==0.11.3`,
`novasvg==0.11.5` y QuickJS-ng disponen de wheels compatibles con Python 3.12 y
Windows x64. No se descarga ningún componente durante la conversión.
El renderizado devuelve SVG: la vista ampliada de Qt lo dibuja como vector,
con zoom sin pixelación. Cada operación se ejecuta en un proceso separado,
con un límite de 180 segundos y sin exponer APIs de red al JavaScript.
La compatibilidad visual de todos los diagramas y el portable aún debe verificarse.

Al migrar desde una versión anterior, usa una carpeta de distribución nueva para
no conservar dependencias antiguas:

```powershell
.\scripts\build.ps1 -OutputDirectory dist-mermaidx
```

Los antiguos recursos locales de `tools\mermaid` y `build\mermaid-runtime.zip`
ya no se utilizan ni se incluyen en el portable.

### MCP local

#### Preparar 2MD

1. Conserva completa la carpeta portable `dist\2MD`, incluidos `2MD-MCP.exe` y
   `_internal`. Si aún no existe, genera la distribución con `.\scripts\build.ps1`.
2. Abre `2MD.exe` y selecciona una carpeta de destino en la ventana principal.
3. En **Configuración → MCP**, activa **MCP local por stdio**, selecciona el
   directorio permitido y guarda. Después puedes cerrar 2MD.

El cliente inicia `2MD-MCP.exe` cuando lo necesita, sin URL ni token. Cada
solicitud comprueba la configuración vigente y solo admite PDF y DOCX del
directorio permitido y sus subcarpetas.

La herramienta `leer_documento` recibe `ruta`, absoluta o relativa al directorio
permitido, y devuelve el Markdown, la ruta del archivo generado y las advertencias.
Las imágenes y demás archivos se guardan en la carpeta de destino; el original no
se modifica. El MCP no utiliza IA ni OCR.

El proceso se ejecuta con los permisos del usuario: la restricción de directorio
no sustituye los permisos del sistema ni constituye un aislamiento frente a
otros procesos locales.

#### OpenCode

En el archivo `opencode.json` de la raíz del proyecto, añade esta configuración.
Para todos los proyectos puedes utilizar `~\.config\opencode\opencode.json`.
Sustituye la ruta por la ubicación real de `2MD-MCP.exe`; en JSON cada
barra invertida de Windows debe escribirse como `\\`.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "2md": {
        "type": "local",
        "command": ["C:\\ruta\\2MD\\2MD-MCP.exe"]
      }
    }
  }
}
```

Si el archivo ya contiene configuración, añade el servidor `2md` al objeto
`mcp.servers` existente sin borrar las demás opciones. Desde el proyecto, ejecuta
`opencode mcp list` para comprobar el estado. Si no aparece, reinicia OpenCode.

#### Roo Code

En el panel MCP de Roo Code, activa los servidores MCP y selecciona
**Edit Project MCP** para abrir o crear `.roo\mcp.json` en la raíz del proyecto.
Para todos los proyectos, usa **Edit Global MCP** en su lugar. Añade:

```json
{
  "mcpServers": {
    "2md": {
      "command": "C:\\ruta\\2MD\\2MD-MCP.exe",
      "timeout": 600
    }
  }
}
```

Sustituye la ruta por la ubicación real y conserva las demás opciones si el
archivo ya existe. `timeout` permite hasta 600 segundos por solicitud; ajusta
ese valor si tus documentos necesitan más tiempo. Comprueba en el panel MCP que
aparecen `2md` y la herramienta `leer_documento`; si no, reconecta el servidor.

En cualquiera de los dos clientes puedes pedir, por ejemplo: «Usa `leer_documento`
para leer `manual.pdf`». La ruta relativa se busca en el directorio permitido,
no en el directorio desde el que se ha lanzado el cliente.

La integración MCP y la distribución portable aún deben verificarse con el
ejecutable generado y un cliente real en Windows limpio.

## Viabilidad y decisiones pendientes

La migración a Xberg está implementada, pero todavía no se han verificado la
fidelidad de extracción ni la distribución portable en Windows.

- **Python, Qt y empaquetado.** Xberg publica un wheel `win_amd64` para Python
  3.10+ ABI3 en su índice de archivo; el proyecto fija la versión 1.3.8 porque
  la 1.3.9 de PyPI no incluye wheel para Windows. PyInstaller incluye Python y
  Qt, pero la extensión Rust de Xberg puede necesitar hooks. Se debe verificar
  primero `--onedir` en Windows limpio.
- **Documentos.** Xberg admite PDF y DOCX y ofrece extracción Markdown e imágenes.
  La integración exporta las imágenes extraídas como recursos referenciados. No se
  ha demostrado que capture todos los elementos de Word, formas o diagramas
  vectoriales, ni que conserve perfectamente orden y tablas complejas; habrá que
  comprobar documentos representativos y avisar de pérdidas. HTML para tablas
  complejas requiere verificar la exportación y la compatibilidad con GitHub.
- **IA y red.** El SDK de OpenAI acepta `base_url` y un cliente HTTP configurable.
  La versión 1.109.1 seleccionada utiliza HTTPX 0.28.1; la documentación actual
  del SDK utiliza HTTPX2. HTTPX documenta proxy Basic y variables de entorno con
  `NO_PROXY`; las exclusiones manuales se configuran explícitamente para hosts e
  IP, no para rangos CIDR. La integración con proxy
  del sistema, excepciones manuales, HTTPS al proxy y errores 407 precisa
  verificación de extremo a extremo con el transporte elegido. Un endpoint
  compatible puede no soportar visión ni parámetros opcionales. Las descargas de
  modelos pueden utilizar otros clientes HTTP: no se asumirá que heredan las
  preferencias del cliente de IA.
- **NTLM y Kerberos.** No están implementados. Las extensiones de autenticación
  de servidor no demuestran soporte de autenticación contra proxy CONNECT;
  ninguna de estas modalidades se anuncia como compatible.
- **TLS y secretos.** `truststore` permite usar CryptoAPI de Windows y un
  `SSLContext`; si se selecciona un archivo CA, se utiliza ese paquete como
  almacén para la conexión en lugar del almacén de Windows. `keyring` se usa
  mediante su backend de Windows, sin alternativa en texto plano; aún hay que
  verificar la integración y que errores y registros no contienen secretos.
  La validación TLS no se deshabilita automáticamente.
- **OCR.** Se desactiva explícitamente para que la conversión no descargue modelos
  ni procese texto de imágenes o páginas escaneadas. Se puede evaluar activarlo
  más adelante, teniendo en cuenta sus dependencias y recursos externos.
- **Mermaid.** `mermaidx` ejecuta Mermaid.js con QuickJS-ng y genera SVG sin
  navegador. El spec incluye sus recursos, fuentes y dependencias nativas; hay
  que verificar sus licencias y el empaquetado final autocontenido. La vista Qt
  usa etiquetas SVG en lugar de HTML para evitar depender de un motor web.
  Las propuestas que requieran etiquetas HTML no compatibles se rechazan
  explícitamente, conservando siempre la imagen original.
  Un renderizado válido no garantiza que el
  diagrama reproduzca fielmente el original: será necesaria revisión humana.
- **Cancelación y concurrencia.** Las tareas de Qt pueden mantener la interfaz
  responsiva, pero la interrupción de una operación Xberg en curso no se garantiza.
  La memoria y la concurrencia deben medirse con documentos representativos.
- **Distribución portable.** Los dos ejecutables comparten una carpeta de
  dependencias; hay que verificar ambos en Windows limpio. La configuración
  permanece fuera de la carpeta de la aplicación.

### Fuentes

- [Xberg: README y formatos](https://github.com/xberg-io/xberg)
- [Xberg: API Python](https://github.com/xberg-io/xberg/tree/v1.3.8/packages/python)
- [Índice de wheels Xberg](https://xberg-io.github.io/python-wheels/simple/xberg/)
- [HTTPX: proxies](https://www.python-httpx.org/advanced/proxies/) y
  [variables de entorno](https://www.python-httpx.org/environment_variables/)
- [SDK OpenAI 1.109.1 y HTTPX](https://github.com/openai/openai-python/blob/v1.109.1/README.md)
- [Almacén nativo de certificados](https://truststore.readthedocs.io/en/latest/)
  y [keyring](https://pypi.org/project/keyring/)
- [mermaidx: API y dependencias](https://pypi.org/project/mermaidx/0.11.3/)
- [Funcionamiento de PyInstaller](https://pyinstaller.org/en/stable/operating-mode.html)
