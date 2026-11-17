# Lógica de negocio de 2MD

Este documento recoge el comportamiento y las decisiones funcionales vigentes.
Sirve de referencia para cambios y migraciones de tecnología: hay que conservar
estas reglas salvo que se acuerde explícitamente cambiar una decisión. No describe
la arquitectura ni obliga a mantener la implementación actual.

## Conversión de documentos

- Se admiten documentos PDF y DOCX. La selección de archivos es temporal; al añadir
  una carpeta desde la aplicación solo se incluyen sus archivos directos, no sus
  subcarpetas. Los documentos duplicados por ruta (ignorando mayúsculas) se añaden
  una sola vez y se conserva el orden.
- La conversión es local y genera Markdown. No modifica el documento de origen.
  Las imágenes extraídas se guardan junto al Markdown en `assets` y se enlazan
  desde este.
- OCR está desactivado: no se extrae texto de imágenes ni de páginas escaneadas.
  Actualmente cada PDF incluye una advertencia sobre esta limitación.
- El usuario elige la carpeta de destino. Una salida anterior solo se reutiliza
  si corresponde al mismo origen, contenido, versión y configuración, y sus
  archivos siguen íntegros. No se sobrescribe una carpeta existente que no pueda
  validarse como resultado reutilizable.
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
- En la revisión manual, el usuario puede editar el Mermaid. Para aceptarlo debe
  validarlo, comparar visualmente el resultado con la imagen y aceptarlo de forma
  explícita. Un cambio posterior requiere volver a validar. El diagrama aceptado
  se inserta junto a la imagen original.
- El Mermaid debe poder validarse y renderizarse. Las propuestas incompatibles con
  el renderizador actual, incluidas las que requieren etiquetas HTML, se rechazan.
  Una validación técnica no garantiza fidelidad visual; la comparación humana es
  necesaria.

## Servidor MCP local

- MCP funciona localmente por stdio y está desactivado por defecto. Cada solicitud
  usa la configuración vigente y solo admite PDF o DOCX ubicados en el directorio
  permitido o sus subcarpetas. Se aceptan rutas relativas a ese directorio o
  absolutas dentro de él; se rechazan rutas fuera de sus límites.
- El resultado se guarda en la carpeta de destino configurada. La herramienta
  devuelve el Markdown, la ruta del Markdown y las advertencias. No ejecuta IA ni
  OCR.
- Requisito funcional: el cliente MCP debe poder acceder a las imágenes extraídas
  del documento, además del Markdown. Devolver únicamente rutas locales o enlaces
  Markdown que el cliente no pueda abrir no satisface el requisito. El mecanismo
  de exposición queda a elección de la implementación MCP.
- Dar acceso a las imágenes al cliente MCP no autoriza a enviarlas a un servicio
  remoto de IA. Ese envío sigue requiriendo consentimiento explícito.
- MCP se ejecuta con los permisos del usuario. La restricción del directorio
  permitido no es un aislamiento del sistema operativo frente a otros procesos.

## Preferencias, secretos y red

- Las preferencias no sensibles se guardan localmente fuera de la carpeta de la
  aplicación. Las credenciales de IA y del proxy se guardan en el almacén seguro
  de Windows; no se guardan en texto plano ni se usa ese formato como alternativa.
- La validación TLS no se desactiva automáticamente. El usuario puede elegir el
  proxy del sistema/entorno, no usar proxy o configurar uno manual, así como un
  archivo de certificados CA.
- NTLM y Kerberos para el proxy no están implementados y no deben anunciarse como
  compatibles.

## Limitaciones actuales, no requisitos funcionales

- Una conversión fallida puede dejar una carpeta de salida incompleta. Como no se
  sobrescriben salidas existentes no reutilizables, esa carpeta puede impedir un
  nuevo intento automático con la misma salida.
- La implementación Python anterior solo devolvía rutas y referencias a imágenes.
  La reimplementación Node incorpora recursos MCP binarios para acceder a ellas;
  su interoperabilidad con clientes reales todavía requiere verificación.
- No está garantizada la extracción fiel de todos los elementos de Word, formas,
  diagramas vectoriales, tablas complejas ni el orden de lectura de todos los
  documentos. Deben probarse documentos representativos antes de prometer esa
  fidelidad.
- La cancelación no garantiza interrumpir una extracción que ya esté ejecutándose.
- El funcionamiento de la distribución portable, la compatibilidad completa con
  redes corporativas y la fidelidad general de extracción aún requieren
  verificación.
