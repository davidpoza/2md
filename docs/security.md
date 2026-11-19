# Seguridad de 2MD

Este documento recoge el análisis de seguridad del motor de conversión, las medidas
que aplica 2MD y cómo comprobarlas. Las reglas funcionales relacionadas con la
seguridad (consentimiento para IA, directorio permitido del MCP, renderizado aislado
de Mermaid) están en [logic.md](logic.md) y no se repiten aquí.

## Objetivo

La conversión de PDF y DOCX debe ser local: no debe abrir conexiones de red, enviar
documentos o métricas a terceros, descargar modelos ni seguir los enlaces que
contienen los documentos. Los documentos se consideran no fiables.

## Motor de conversión: Xberg

2MD usa `@xberg-io/xberg` 1.3.10, una biblioteca en Rust cargada mediante NAPI-RS
como binario nativo (`@xberg-io/xberg-<plataforma>`). El análisis corresponde al
código fuente de la etiqueta `v1.3.10` de
[github.com/xberg-io/xberg](https://github.com/xberg-io/xberg) y al binario de
Linux publicado en npm. No es una auditoría completa: se ha revisado el camino que
sigue la llamada de 2MD y todo lo que puede abrir la red.

### Copia local en el repositorio

Xberg no se descarga del registro de npm: se instala desde copias guardadas en
`vendor/xberg/`, de modo que el código que se ejecuta es el que se ha revisado y no
puede cambiar sin un commit.

| Archivo | Contenido | SHA-512 (base64) |
|---|---|---|
| `xberg-io-xberg-1.3.10.tgz` | Cargador JavaScript, **modificado** (ver abajo) | `sc+2MJDM3fupW1wf1s55wreSiJcM2hyyDu3e5v4ivFKihppKgt88NI8XXMXNhJsrHLcGNztZIX47uAAGYeG4Lg==` |
| `xberg-io-xberg-linux-x64-gnu-1.3.10.tgz` | Binario de Linux x64 (glibc), idéntico al publicado | `d+WifY8sTToRrsEeadFOiScfjro15UjCuEarPwzdumX80MJky21DOFflrJvpV4fCR1llMFVJyrzC14q3ZGIbEA==` |
| `xberg-io-xberg-win32-x64-msvc-1.3.10.tgz` | Binario de Windows x64, idéntico al publicado | `JypK+tfBKWPGuHbz+3hcSKejcboINisr5Jmt7B25AymaN3rz+MiXbz3lVHgZvzYDKuH17fFigHi5P3SvHfmUmA==` |

- `package.json` declara el cargador en `dependencies` y los dos binarios en
  `optionalDependencies`, todos con rutas `file:`. `package-lock.json` fija su
  integridad, y npm rechaza la instalación si un archivo no coincide.
- El cargador publicado declara en `optionalDependencies` los binarios de seis
  plataformas, que npm descargaría del registro. Esa lista es lo único que se ha
  eliminado de su `package.json`; el resto de archivos del paquete es idéntico al
  publicado. Así no se instala nada de Xberg desde el registro.
- No se incluyen las variantes musl, macOS ni ARM: Electron solo funciona con glibc
  y 2MD solo se distribuye para Windows y Linux x64. Además, si se incluyeran como
  sustituciones locales, npm eliminaría del lockfile la de `libc` distinta a la del
  sistema y `npm ci` fallaría.
- `.gitattributes` marca `vendor/` como binario para que Git no altere los archivos
  (por ejemplo, con la conversión de saltos de línea en Windows).
- Los dos binarios se comprobaron contra el `dist.integrity` del registro el
  2026-11-19.

Para comprobar que el cargador solo difiere del publicado en esa lista:

```
mkdir publicado local
npm pack @xberg-io/xberg@1.3.10 --pack-destination publicado
tar xzf publicado/xberg-io-xberg-1.3.10.tgz -C publicado
tar xzf vendor/xberg/xberg-io-xberg-1.3.10.tgz -C local
diff -r publicado/package local/package
```

El único cambio que debe aparecer es la eliminación de `optionalDependencies` en
`package.json`.

### Capacidades compiladas

El binding de Node (`crates/xberg-node/Cargo.toml`) se compila con casi todas las
funciones, tanto en Linux (`full`) como en Windows (`windows-target`): crawling de
URLs, clientes LLM, servidor HTTP y MCP, OpenTelemetry, descarga de modelos de
Hugging Face, OCR, NER, embeddings y transcripción. En Windows no se incluye el motor
PDF `pdfium` (C++), solo el nativo.

Por tanto, el binario **puede** conectarse a la red. Que la conversión sea local
depende de la configuración con la que 2MD llama a `extract`.

### Puntos de red y cómo los evita 2MD

| Mecanismo | Qué lo activa en Xberg | Medida en 2MD |
|---|---|---|
| Descarga de una URL | Una `uri` que empieza por `http://` o `https://` (`engine/extract_impl.rs`) | Se pasa siempre la ruta local resuelta con `realpath` |
| Seguimiento de enlaces del documento | `url.crawl.follow_document_urls`; se evalúa tras cada extracción, también local | `followDocumentUrls: false` explícito |
| URI `file://` | `url.allow_file_uris` | `allowFileUris: false` explícito |
| OCR y sus modelos (Tesseract, Paddle, Hugging Face) | Pipeline OCR del PDF | `disableOcr: true` corta antes que cualquier otra rama, incluido el OCR de páginas escaneadas |
| Modelo de layout | `use_layout_for_markdown` y `layout` | `useLayoutForMarkdown: false` explícito |
| LLM, NER, resumen, traducción, embeddings, captioning | Cada uno requiere su configuración | No se configuran; su valor por defecto es `None` |
| Imágenes enlazadas en DOCX (`r:link`) | Solo se buscan dentro del ZIP | Nunca se descargan |

Las opciones se fijan de forma explícita en `app/conversion.js`, aunque coincidan
con los valores por defecto de Xberg 1.3.10, para que un cambio de esos valores en
una versión futura no active funciones de red. El valor por defecto de
`follow_document_urls` procede de la biblioteca externa `crawlberg`, no de Xberg.

Si se sigue un enlace, Xberg aplica una política SSRF que rechaza direcciones
locales y privadas, pero sí se conecta a direcciones públicas. Se ha comprobado que,
con el seguimiento activado, un enlace a `example.com` en un DOCX genera una petición
real a Internet.

### Telemetría

- Xberg instrumenta métricas y trazas con OpenTelemetry, pero no incluye ningún
  exportador OTLP; la dependencia no está en su `Cargo.toml`.
- Las métricas usan el medidor global, que no hace nada mientras nadie instale uno
  real. Solo lo instala el servidor HTTP de Xberg (`api/router.rs`) para publicar
  `/metrics` en local. 2MD no arranca ese servidor.
- El cliente `xet` de Hugging Face tiene su propia telemetría, que solo se usa al
  descargar modelos.
- En el binario no aparecen direcciones de envío de xberg.io ni servicios como
  PostHog, Mixpanel o Sentry.

### Configuración externa

- Xberg puede cargar `xberg.toml`, `xberg.yaml`, `xberg.yml` o `xberg.json` desde las
  carpetas superiores o la configuración del usuario, y aplicar variables `XBERG_*`
  (por ejemplo `XBERG_LLM_BASE_URL`). Ambas cosas solo ocurren en su servidor HTTP
  (`api/startup.rs`, `api/config.rs`), no en `extract`.
- `PDFIUM_DYNAMIC_LIB_PATH` carga una biblioteca nativa, pero solo con el motor
  `pdfium`, que 2MD no selecciona y que en Windows no está compilado.
- `ORT_DYLIB_PATH` carga ONNX Runtime, que solo usan funciones de IA que 2MD no
  activa.
- El cargador JavaScript de NAPI-RS carga con `require` cualquier módulo indicado en
  `NAPI_RS_NATIVE_LIBRARY_PATH`. **2MD elimina esa variable** en
  `app/xberg-environment.js`, que `app/conversion.js` importa antes que Xberg. Así
  cubre la aplicación, los lanzadores MCP y los tests.
- El cargador ejecuta `ldd --version` en Linux para distinguir glibc de musl.

### Documentos maliciosos

- El parser PDF nativo (`xberg-native-pdf`) es Rust puro, sin bloques `unsafe`, y
  descomprime con `zlib-rs`.
- El XML de DOCX se procesa con `quick-xml` y `roxmltree`, que no resuelven entidades
  externas (sin XXE).
- Las rutas internas del ZIP se validan con `resolve_container_entry`, sin poder salir
  del paquete. Las imágenes tienen tamaño máximo y la lectura se limita al tamaño
  declarado (corrección de GHSA-85w9-wqcq-x48r).
- Límites por defecto (`extractors/security.rs`): archivo de 500 MiB, compresión 100×,
  10.000 entradas, profundidad XML 1024, contenido de 100 MiB, 100.000 celdas de
  tabla, 50 MiB por archivo incrustado y profundidad de archivos anidados 3.
- Tiempo máximo de extracción: 600 s, fijado de forma explícita en 2MD. Al vencer,
  se cancela la espera, pero el parseo del PDF corre en un hilo bloqueante que no
  comprueba la cancelación en cada operación: un PDF patológico puede seguir usando
  CPU hasta terminar la página en curso.

### Discrepancias de la documentación de Xberg

El `SECURITY.md` de Xberg indica un tiempo máximo por defecto de 60 s (el código usa
600 s) y soporte para versiones 5.x (la versión actual es 1.3). No debe usarse para
decidir si una versión recibe parches.

### Dependencias

El `deny.toml` de Xberg ignora 10 avisos de RustSec:

| Aviso | Paquete | Relevancia para 2MD |
|---|---|---|
| RUSTSEC-2026-0115, -0116, -0117 | `imageproc` (comprobaciones de límites) | Solo lo usan los crates de OCR (`sceptre`, `xberg-paddle-ocr`), que 2MD no ejecuta |
| RUSTSEC-2026-0176, -0177 | `pyo3` | Solo afecta al binding de Python |
| RUSTSEC-2024-0436, RUSTSEC-2025-0119, RUSTSEC-2020-0144, RUSTSEC-2026-0192, RUSTSEC-2026-0206 | `paste`, `number_prefix`, `lzw`, `ttf-parser`, `rustybuzz` | Paquetes sin mantenimiento, sin vulnerabilidad concreta |

No se ha ejecutado `cargo audit` sobre las 1.140 dependencias de `Cargo.lock`.

## Tests de seguridad

Los de red están en `tests-node/network.test.js`. Usan `tests-node/network-child.js`,
que convierte documentos con `convertDocument` (la misma función que la app y el
MCP), y `tests-node/fixtures.js`, que genera un PDF y un DOCX con imagen y enlace.
La copia local de Xberg se comprueba en `tests-node/vendor.test.js`.

### Ejecución

En Linux y en Windows, desde la raíz del proyecto:

```
node --test tests-node/network.test.js tests-node/vendor.test.js
```

También se ejecutan con `npm test`. Ejecuta antes `npm ci` en ese mismo sistema para
que se instale y compruebe su binario de Xberg; no copies `node_modules` entre
sistemas. Conviene ejecutarlos cada vez que se actualice `@xberg-io/xberg`.

`npm ci` usa `package-lock.json`. Si `npm` es un alias de pnpm, ejecuta el npm real
(`command npm ci` en zsh o bash). pnpm también instala Xberg desde `vendor/`, pero no
usa el lockfile de npm y, en versiones recientes, rechaza la dependencia git de
`electron-builder` salvo con `--config.block-exotic-subdeps=false`.

### Qué comprueban

1. **`conversion opens no network connections, even when proxies, model hubs and
   linked documents are reachable`**
   - Un servidor trampa local se configura como proxy (`HTTP_PROXY`, `HTTPS_PROXY`,
     `ALL_PROXY`, en mayúsculas y minúsculas) y como `HF_ENDPOINT`. Debe recibir 0
     conexiones.
   - Se vigilan los sockets de red del proceso: en Linux cruzando `/proc/<pid>/fd`
     con `/proc/<pid>/net/{tcp,tcp6,udp,udp6}` cada 2 ms; en Windows con
     `netstat -ano` filtrado por PID. No debe aparecer ninguno. El proceso espera a
     una lectura completa antes de salir, para detectar conexiones que sigan
     abiertas.
   - Los documentos enlazan a la trampa. Xberg rechaza ese destino por su política
     SSRF antes de conectar, pero registra el intento como error y 2MD lo copia a
     las advertencias; el test exige que ninguna advertencia mencione el enlace.
     Actualmente solo el DOCX ejercita este caso: Xberg no extrae los enlaces de
     las anotaciones PDF con la configuración de 2MD.
2. **`conversion works without any network interface`** (solo Linux): convierte en
   un espacio de nombres sin red (`unshare -rn`). Se omite en Windows o si el sistema
   no permite crear ese espacio (`unshare -rn true` falla).
3. **`conversion ignores a native library override for Xberg`**: apunta
   `NAPI_RS_NATIVE_LIBRARY_PATH` a un módulo que crea un archivo testigo al cargarse
   y comprueba que no se crea.
4. **`every Xberg package is installed from the vendored tarballs with matching
   integrity`** (`tests-node/vendor.test.js`): comprueba en `package-lock.json` que
   los únicos paquetes de Xberg son el cargador y los binarios de Linux x64 y Windows
   x64, que todos se resuelven desde `vendor/xberg/`, que su versión es
   `XBERG_VERSION`, que no declaran dependencias de plataforma remotas y que el
   SHA-512 de cada archivo coincide con la integridad del lockfile.

### Límites

- La vigilancia de sockets es por muestreo: una conexión muy breve entre dos
  lecturas puede escaparse, sobre todo en Windows, donde cada `netstat` tarda
  bastante. La trampa y la prueba sin red cubren ese hueco en parte.
- En Windows las consultas DNS las hace un servicio del sistema, no el proceso, y no
  aparecen en su `netstat`.
- La trampa solo detecta clientes HTTP que respetan las variables de proxy.
- Para una garantía completa: registrar llamadas al sistema
  (`strace -f -e trace=connect` en Linux, Process Monitor en Windows) o bloquear la
  salida del proceso con un firewall.
- Algunos antivirus o firewalls abren conexiones dentro de los procesos que vigilan;
  revisa el destino de un socket inesperado antes de atribuirlo a Xberg.

### Controles negativos

Para confirmar que los tests detectan fallos, aplica temporalmente uno de estos
cambios, comprueba que el test indicado falla y deshazlo:

| Cambio temporal | Test que debe fallar | Mensaje |
|---|---|---|
| `followDocumentUrls: true` en `app/conversion.js` | 1 | `Xberg intentó seguir un enlace del documento` |
| Quitar `import './xberg-environment.js'` de `app/conversion.js` | 3 | `Se cargó la biblioteca indicada por NAPI_RS_NATIVE_LIBRARY_PATH` |
| Añadir `const { createSocket } = await import('node:dgram'); createSocket('udp4').bind(0);` antes del `process.stdout.write` de `tests-node/network-child.js` | 1 | `El proceso de conversión abrió sockets de red` |
| Cambiar un byte de un archivo de `vendor/xberg/` | 4 | `no coincide con su integridad` |

## Al actualizar Xberg

1. Revisa en el `CHANGELOG.md` de Xberg cambios en valores por defecto de OCR,
   layout, URL o crawling, y en el cargador NAPI-RS. Repite el análisis de este
   documento sobre la etiqueta de la nueva versión.
2. Descarga los tres paquetes de la nueva versión `X.Y.Z` con el npm real:
   ```
   npm pack @xberg-io/xberg@X.Y.Z @xberg-io/xberg-linux-x64-gnu@X.Y.Z @xberg-io/xberg-win32-x64-msvc@X.Y.Z
   ```
3. Comprueba cada archivo contra `npm view <paquete>@X.Y.Z dist.integrity`, que debe
   ser `sha512-` seguido del SHA-512 en base64 del archivo
   (`openssl dgst -sha512 -binary <archivo> | base64`).
4. Extrae el cargador, elimina `optionalDependencies` de su `package.json` y vuelve a
   empaquetarlo con `npm pack` desde el directorio extraído.
5. Sustituye los archivos de `vendor/xberg/`, actualiza las rutas de `package.json`
   y ejecuta `npm install --package-lock-only`.
6. Comprueba que las opciones de `app/conversion.js` siguen existiendo con el mismo
   nombre en `index.d.ts`; Xberg ignora sin error los campos desconocidos.
7. Actualiza `XBERG_VERSION` en `app/conversion.js`, la tabla de copias locales y el
   resto de este documento.
8. Ejecuta `npm ci` y los tests de seguridad en Linux y en Windows, y los controles
   negativos.

## Pendiente de verificar

- La equivalencia entre los binarios publicados en npm y el código fuente.
- El empaquetado con electron-builder desde la copia local: en el entorno de la
  revisión la compilación de Linux falla antes de empaquetar con un error
  `ENOENT` en `node_modules/@antfu/install-pkg`, que también se produce sin la copia
  local.
- El binario de Windows (`@xberg-io/xberg-win32-x64-msvc`): los tests deben
  ejecutarse allí.
- Una auditoría de vulnerabilidades de todas las dependencias Rust.
- El código de Xberg fuera del camino de 2MD (servidor HTTP, MCP propio, crawling).
