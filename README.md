# 2MD

Aplicación de escritorio para convertir documentos empresariales a Markdown.

## Estado: implementación parcial

La ventana permite seleccionar archivos DOCX y PDF, añadir los archivos de una carpeta
sin recorrer subcarpetas, arrastrarlos y elegir una carpeta de destino. La selección
es temporal; el destino y el límite de concurrencia se guardan en
`%APPDATA%\2MD\settings.json`. Este archivo no almacena credenciales.

Se han implementado la conversión local por lotes mediante Docling, workers con
concurrencia configurable, cancelación cooperativa y reintentos, exportación Markdown
con imágenes referenciadas, informes de conversiones completadas y reutilización
de resultados cuyo contenido y configuración no han cambiado. No se sobrescriben
carpetas existentes que no se puedan reutilizar. Una exportación fallida puede dejar
una carpeta incompleta; los errores no producen todavía un informe individual.

Los PDF requieren seleccionar una carpeta de modelos Docling ya descargados en
Configuración. Esto evita depender de descargas automáticas mientras no se integre
su transporte con la configuración de red. **No se realiza OCR**: el texto de
imágenes y páginas escaneadas no se extrae y cada PDF genera una advertencia.
La cancelación espera a que termine
la operación Docling en curso. El cálculo de hash de los modelos puede ser costoso.

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
pytest-qt y Ruff. Docling y docling-core están fijados a las versiones 2.150.0 y
2.106.0 utilizadas como referencia para las APIs de esta fase. `uv.lock` fija
las dependencias resueltas; la distribución todavía no está verificada.

### Empaquetado de desarrollo

`scripts\build.ps1` genera únicamente la carpeta portable `dist\2MD`, con
`2MD.exe` y `2MD-MCP.exe`. Ambos comparten sus dependencias y la carpeta debe
copiarse completa. El script no elimina un `dist\2MD.exe` antiguo que ya exista.

```powershell
.\scripts\build.ps1
```

En compilaciones posteriores puede añadirse `-ReuseMermaid` para reutilizar el
archivo ya creado. No se debe utilizar si se han modificado el renderizador,
las dependencias, Node o Chromium.
Tampoco debe reutilizarse un archivo generado antes de aplicar cambios al guion de
empaquetado: el runtime Mermaid ya no incluye los archivos de depuración `.map`.

Requiere uv, Python 3.12 x64 y los modelos de diseño y tablas de Docling obtenidos
previamente en `resources\models`, por ejemplo mediante
`docling-tools models download layout tableformer -o resources\models`.
No requiere modelos de OCR. Los modelos no están incluidos en el
repositorio. Se incorporan únicamente Heron con Transformers y TableFormer Accurate;
las variantes ONNX y Fast no se utilizan. Los modelos incluidos se usan por defecto
si el usuario no selecciona otros. También requiere `tools\mermaid\node_modules`,
`tools\mermaid\runtime\node.exe` y Chromium en `tools\mermaid\browser`. El guion
agrupa estos recursos en un archivo para evitar que PyInstaller clasifique cada
archivo individualmente. En el ejecutable se extraen temporalmente la primera vez
que se valida un diagrama; esa primera validación puede tardar y requiere espacio
temporal adicional. El guion **no se ha validado** y no constituye
una distribución final. Se deben comprobar también las licencias y el funcionamiento
sin conexión en Windows limpio.

Para preparar el renderizador de desarrollo con Node 22.13 o posterior:

```powershell
npm ci --prefix tools\mermaid --ignore-scripts
$env:PUPPETEER_CACHE_DIR = (Join-Path (Get-Location) 'tools\mermaid\browser')
.\tools\mermaid\node_modules\.bin\puppeteer.cmd browsers install chrome-headless-shell
New-Item -ItemType Directory -Force tools\mermaid\runtime
Copy-Item (Get-Command node.exe).Source tools\mermaid\runtime\node.exe
```

La preparación descarga componentes en el equipo de desarrollo, no durante la
conversión. No se debe deshabilitar la validación de certificados para las descargas.

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

La documentación disponible respalda la viabilidad general, no garantiza la
compatibilidad del conjunto concreto ni la fidelidad total. Se debe resolver y
verificar el conjunto de dependencias en Windows x64 antes de fijar sus versiones.

- **Python, Qt y empaquetado.** Docling admite Python 3.12 y Windows; PySide6 y
  PyInstaller documentan soporte de Windows. PyInstaller incluye Python y Qt,
  pero las importaciones dinámicas, dependencias nativas y datos de Docling pueden
  necesitar hooks. Se debe verificar primero `--onedir` y después `--onefile` en
  Windows 10 y 11 limpios.
- **Documentos.** Docling admite PDF y DOCX. El ejemplo oficial de PDF configura
  `generate_picture_images` y exporta imágenes referenciadas. No se ha demostrado
  que capture todos los elementos de Word, formas o diagramas vectoriales, ni
  que conserve perfectamente orden y tablas complejas; habrá que comprobar
  documentos representativos y avisar de pérdidas. HTML para tablas complejas
  requiere verificar la exportación y la compatibilidad con GitHub.
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
- **Modelos Docling.** Por defecto pueden descargarse al primer uso. Docling
  permite obtenerlos por adelantado y configurar `artifacts_path`. Hay que incluir
  los modelos exactos seleccionados y sus licencias en la distribución, e
  investigar tamaño y rutas, sin depender de descargas silenciosas.
- **Mermaid.** Mermaid CLI necesita Node, Puppeteer y un navegador compatible;
  PyInstaller no los incorpora automáticamente. Hay que distribuir y verificar
  estos componentes o una alternativa equivalente, sus licencias y el aislamiento
  del renderizado de contenido no confiable. No se ha demostrado aún el
  empaquetado final autocontenido. Un renderizado válido no garantiza que el
  diagrama reproduzca fielmente el original: será necesaria revisión humana.
- **Cancelación y concurrencia.** Las tareas de Qt pueden mantener la interfaz
  responsiva, pero la interrupción de una operación Docling en curso depende de
  sus APIs; no se garantiza una cancelación inmediata. La memoria y los modelos
  compartidos impondrán límites a la concurrencia que deberán medirse.
- **Distribución portable.** Los dos ejecutables comparten una carpeta de
  dependencias; hay que verificar ambos en Windows limpio. La configuración
  permanece fuera de la carpeta de la aplicación.

### Fuentes

- [Formatos de Docling](https://docling-project.github.io/docling/usage/supported_formats/)
- [Opciones y modelos locales de Docling](https://docling-project.github.io/docling/usage/advanced_options/)
- [Ejemplo oficial de extracción de figuras PDF](https://github.com/docling-project/docling/blob/main/docs/examples/export_figures.py)
- [HTTPX: proxies](https://www.python-httpx.org/advanced/proxies/) y
  [variables de entorno](https://www.python-httpx.org/environment_variables/)
- [SDK OpenAI 1.109.1 y HTTPX](https://github.com/openai/openai-python/blob/v1.109.1/README.md)
- [Almacén nativo de certificados](https://truststore.readthedocs.io/en/latest/)
  y [keyring](https://pypi.org/project/keyring/)
- [Mermaid CLI: dependencias](https://github.com/mermaid-js/mermaid-cli/blob/master/package.json)
- [Funcionamiento de PyInstaller](https://pyinstaller.org/en/stable/operating-mode.html)
