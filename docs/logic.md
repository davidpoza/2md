# Lógica de negocio de 2MD

Este documento recoge el comportamiento y las decisiones funcionales vigentes.
Sirve de referencia para cambios y migraciones de tecnología: hay que conservar
estas reglas salvo que se acuerde explícitamente cambiar una decisión. No describe
la arquitectura ni obliga a mantener la implementación actual.

## Conversión de documentos

- Se admiten documentos PDF y DOCX. La selección de archivos es temporal; al añadir
  una carpeta desde la aplicación solo se incluyen sus archivos directos, no sus
  subcarpetas. Los documentos duplicados por ruta (ignorando mayúsculas) se añaden
  una sola vez y se conserva el orden. Se pueden añadir archivos y carpetas
  mediante sus botones o arrastrándolos a la ventana.
- La conversión es local y genera Markdown. No modifica el documento de origen.
  Las imágenes extraídas se guardan junto al Markdown en `assets` y se enlazan
  desde este.
- OCR está desactivado: no se extrae texto de imágenes ni de páginas escaneadas.
  Actualmente cada PDF incluye una advertencia sobre esta limitación. No se
  descargan modelos OCR ni recursos Mermaid durante la conversión.
- El usuario elige la carpeta de destino. Una salida anterior solo se reutiliza
  si corresponde al mismo origen, contenido, versión y configuración, y sus
  archivos siguen íntegros. No se sobrescribe una carpeta existente que no pueda
  validarse como resultado reutilizable. Las salidas de versiones anteriores no
  se reutilizan automáticamente ni se sobrescriben.
- Cada resultado se organiza en un subdirectorio propio del destino con su
  Markdown y `conversion-report.json`; las imágenes se conservan en `assets`
  y los diagramas guardados en `diagrams`.
- **Abrir carpeta destino**, junto al botón **Seleccionar** de la fila de destino,
  abre en el explorador la carpeta de destino configurada que aparece en la
  ventana principal, no la subcarpeta de un documento. Está desactivado mientras
  no haya un destino seleccionado y se puede utilizar durante un lote. Los fallos
  al abrir se notifican al usuario.
- Las conversiones completadas generan un informe con el origen, estado,
  advertencias, versiones, duración y archivos de salida. Los errores se muestran
  en la aplicación; actualmente no generan un informe individual de conversión.

## Procesamiento por lotes

- Se puede procesar más de un documento con concurrencia configurable. La
  cancelación impide iniciar los documentos pendientes y solicita detener los
  trabajos activos; una extracción en curso puede tener que terminar primero.
- Se pueden reintentar documentos con error o cancelados. También son reintentables
  los resultados cuyo análisis automático de imágenes falló. Los resultados
  completos sin errores no se vuelven a procesar como fallidos.
- La lista de documentos de la sesión no se conserva al cerrar la aplicación; sí
  se conservan las preferencias y los resultados de conversión válidos en destino.

## IA y diagramas

- La IA está desactivada por defecto. La conversión normal no envía documentos ni
  imágenes a un servicio remoto.
- Antes de enviar una imagen y el contexto cercano del Markdown a IA, se requiere
  confirmación explícita. El análisis automático también requiere activación y
  confirmación para cada lote. Si el endpoint usa HTTP sin cifrar, se advierte que
  tanto el contenido enviado como la API Key viajarán sin cifrado.
- La IA puede proponer un diagrama Mermaid, pero la propuesta no sustituye la
  imagen original. Las propuestas automáticas quedan marcadas como pendientes de
  revisión; una propuesta no fiable no se inserta.
- Cada propuesta representa exclusivamente su imagen. El contexto auxiliar excluye
  los bloques de código y los diagramas ya generados, antes de limitar su longitud,
  para no arrastrar contenido de propuestas anteriores.
- En la revisión manual, el usuario puede editar el Mermaid. Para aceptarlo debe
  validarlo, comparar visualmente el resultado con la imagen y aceptarlo de forma
  explícita. Un cambio posterior requiere volver a validar. El diagrama aceptado
  se inserta junto a la imagen original.
- La revisión muestra todos los diagramas y su estado en una tabla. Mientras la
  ventana permanece abierta, navegar o guardar otro diagrama conserva los
  borradores, validaciones, vistas previas y posiciones de los visores de cada uno.
  Las operaciones en curso muestran un indicador de carga y bloquean la edición.
- Actualizar manualmente un diagrama reemplaza su archivo Mermaid de destino y su
  bloque en el Markdown, sin duplicarlo ni modificar la imagen original. Esta
  sobrescritura no se aplica a carpetas de conversión no reutilizables ni permite
  que el análisis automático sustituya un diagrama existente.
- El original y el resultado se pueden inspeccionar con visores interactivos:
  zoom bajo el cursor, desplazamiento por arrastre, ajuste, tamaño real y
  comparación ampliada a pantalla completa.
- El Mermaid debe poder validarse y renderizarse. Las propuestas incompatibles con
  el renderizador actual, incluidas las que requieren etiquetas HTML, se rechazan.
  Una validación técnica no garantiza fidelidad visual; la comparación humana es
  necesaria.
- El renderizado es local, en una ventana aislada sin Node ni acceso remoto, y
  tiene un límite de 180 segundos. No se admiten bloques Markdown, HTML, enlaces
  interactivos ni directivas que alteren la configuración del renderizador.

## Configuración de la aplicación

- La configuración se organiza en las pestañas **General**, **Inteligencia
  artificial**, **Red y proxy**, **MCP local** y **Credenciales**. Los checkboxes
  aparecen en la misma línea que sus etiquetas.
- **General** permite ajustar la concurrencia de documentos. **Inteligencia
  artificial** contiene la activación, endpoint, modelo, tiempos de espera,
  reintentos, concurrencia de solicitudes y parámetros opcionales del modelo.
  **Red y proxy** contiene el proxy, exclusiones y archivo CA. **MCP local**
  contiene su activación y directorio permitido. **Credenciales** permite
  introducir la API Key y la contraseña del proxy, ocultas por defecto, y
  mostrarlas explícitamente si se desea.
- Cambiar de pestaña conserva los campos editados. **Guardar** aplica los campos
  de todas las pestañas; **Cancelar** descarta los cambios no guardados. Las
  credenciales introducidas se borran de los controles al cerrar la ventana.
- Las pestañas se pueden recorrer con las flechas izquierda/derecha e Inicio/Fin.
  Las comprobaciones de límites de los campos muestran la pestaña correspondiente
  antes de señalar el primer valor inválido.
- Las pruebas de modelo y visión están en **Inteligencia artificial** y la prueba
  de red en **Red y proxy**. Utilizan la configuración guardada, no los cambios
  pendientes, y requieren consentimiento explícito. La prueba de visión envía una
  imagen sintética de un píxel, no un documento del usuario.
- El endpoint de IA debe ser compatible con chat completions y aceptar imágenes
  para proponer diagramas. Un endpoint compatible puede no soportar visión ni
  todos los parámetros opcionales.

## Servidor MCP local

- MCP funciona localmente por stdio y está desactivado por defecto. Cada solicitud
  usa la configuración vigente y solo admite PDF o DOCX ubicados en el directorio
  permitido o sus subcarpetas. Se aceptan rutas relativas a ese directorio o
  absolutas dentro de él; se rechazan rutas fuera de sus límites.
- El resultado se guarda en la carpeta de destino configurada. La herramienta
  devuelve el Markdown, la ruta del Markdown y las advertencias. No ejecuta IA ni
  OCR.
- La herramienta se llama `leer_documento` y recibe un único argumento `ruta`.
  Devuelve `markdown`, `archivo_markdown`, `advertencias` e `imagenes`.
- Requisito funcional: el cliente MCP debe poder acceder a las imágenes extraídas
  del documento, además del Markdown. Devolver únicamente rutas locales o enlaces
  Markdown que el cliente no pueda abrir no satisface el requisito. El mecanismo
  de exposición queda a elección de la implementación MCP.
- En la implementación vigente, el Markdown devuelto referencia las imágenes
  mediante URI `2md://images/...`. Cada imagen se anuncia como `resource_link` y
  se puede obtener por `resources/read`, como contenido base64 con su MIME.
  El cliente debe admitir recursos MCP. Estos recursos pertenecen a la sesión
  stdio y dejan de estar disponibles si cambia su integridad o autorización.
  El Markdown guardado en disco conserva sus enlaces relativos a `assets`.
- Dar acceso a las imágenes al cliente MCP no autoriza a enviarlas a un servicio
  remoto de IA. Ese envío sigue requiriendo consentimiento explícito.
- MCP se ejecuta con los permisos del usuario. La restricción del directorio
  permitido no es un aislamiento del sistema operativo frente a otros procesos.

### Uso desde clientes MCP

Abre la aplicación, selecciona un destino y activa MCP en **Configuración →
MCP local**, indicando el directorio permitido. Guarda los cambios; después puedes
cerrar la aplicación. El cliente inicia el lanzador MCP por stdio cuando lo
necesita, sin URL ni token. En Linux, el `command` es la ruta de
`dist-linux-mcp/2MD/2MD-MCP` en lugar del EXE. Conserva completa su distribución separada.

Para clientes con configuración `mcpServers`, como Roo Code, utiliza una entrada
equivalente a esta, sustituyendo la ruta por la real y conservando los demás
servidores:

```json
{
  "mcpServers": {
    "2md": {
      "command": "C:\\ruta\\dist-node-mcp\\2MD\\2MD-MCP.exe",
      "timeout": 600
    }
  }
}
```

En Roo Code se puede editar la configuración del proyecto desde **Edit Project
MCP**, en `.roo\mcp.json`, o la configuración global desde **Edit Global MCP**.
Activa los servidores MCP, reconecta si es necesario y comprueba que aparecen
`2md` y `leer_documento`. Ajusta el tiempo de espera del cliente a tus documentos.

En [OpenCode](https://opencode.ai/docs/mcp-servers/), la configuración local usa
`mcp.servers` en `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "2md": {
        "type": "local",
        "command": ["C:\\ruta\\dist-node-mcp\\2MD\\2MD-MCP.exe"]
      }
    }
  }
}
```

`opencode mcp list` permite comprobar la conexión. En cualquiera de los clientes
puedes solicitar «Usa `leer_documento` para leer `manual.pdf`». Las rutas relativas
se resuelven desde el directorio permitido configurado, no desde el directorio
de trabajo del cliente. La interoperabilidad con clientes reales sigue pendiente
de verificación.

## Preferencias, secretos y red

- Las preferencias no sensibles se guardan localmente fuera de la carpeta de la
  aplicación, en `%APPDATA%\2MD\settings.json` en Windows y en
  `$XDG_CONFIG_HOME/2MD/settings.json` (por defecto `~/.config`) en Linux. Las
  credenciales de IA y del proxy se guardan en Windows Credential Manager, con los
  destinos `2MD/api` y `2MD/proxy`, o en Linux en Secret Service, con los servicios
  `2MD/api` y `2MD/proxy` y el usuario `2MD`; no se guardan en texto plano ni se
  usa ese formato como alternativa.
  Dejar los campos de credenciales vacíos al guardar conserva las existentes.
- La validación TLS no se desactiva automáticamente. El usuario puede elegir el
  proxy del sistema/entorno, no usar proxy o configurar uno manual, así como un
  archivo de certificados CA.
- El proxy manual admite autenticación Basic. Las exclusiones admiten hosts,
  dominios, direcciones IP y `*`, no rangos CIDR. No debe suponerse que otros
  clientes HTTP externos hereden estas preferencias.
- NTLM y Kerberos para el proxy no están implementados y no deben anunciarse como
  compatibles.

## Distribución

- La aplicación gráfica se distribuye como carpeta portable para Windows x64, con
  `2MD.exe`, y para Linux x64, con el ejecutable `2MD`, junto con sus recursos y
  dependencias nativas. Se debe copiar la carpeta completa; el ejecutable no
  funciona de forma independiente.
- El runtime se carga directamente desde esa carpeta, sin autoextraer la
  distribución a un directorio temporal en cada arranque. No requiere instalación
  ni permisos de administrador, ni Node, Python o Qt instalados en destino.
  Las preferencias y las credenciales conservan sus ubicaciones habituales.
- MCP se distribuye por separado, con su lanzador de consola (`2MD-MCP.exe` en
  Windows, `2MD-MCP` en Linux) y runtime en una carpeta completa, para mantener
  el transporte stdio.
- Las carpetas `win-unpacked` y `linux-unpacked` son intermedios que el script
  renombra a `2MD` al completar el empaquetado. El lanzador MCP utiliza su propia copia del Node
  integrado en Electron y mantiene stdout reservado al protocolo.
- Desde las fuentes, con las dependencias instaladas, `npm start` abre la
  aplicación y `npm run mcp` inicia únicamente el servidor stdio con Node.
  MCP sigue requiriendo activación y directorios configurados previamente.

## Limitaciones actuales, no requisitos funcionales

- Una conversión fallida puede dejar una carpeta de salida incompleta. Como no se
  sobrescriben salidas existentes no reutilizables, esa carpeta puede impedir un
  nuevo intento automático con la misma salida.
- El acceso a las imágenes mediante recursos MCP binarios todavía requiere
  verificar la interoperabilidad con clientes reales.
- No está garantizada la extracción fiel de todos los elementos de Word, formas,
  diagramas vectoriales, tablas complejas ni el orden de lectura de todos los
  documentos. Deben probarse documentos representativos antes de prometer esa
  fidelidad.
- La cancelación no garantiza interrumpir una extracción que ya esté ejecutándose.
- El funcionamiento de la distribución portable, la compatibilidad completa con
  redes corporativas y la fidelidad general de extracción aún requieren
  verificación.
