import path from 'node:path';
import { stat, realpath, mkdir, readFile, writeFile } from 'node:fs/promises';
import './xberg-environment.js';
import { extract } from '@xberg-io/xberg';
import { confined, fileHash, outputHashes, readJson, sha256, supported } from './files.js';

export const XBERG_VERSION = '1.3.10';
export const APP_VERSION = '0.2.0';
const extensions = new Set(['bmp', 'gif', 'jpeg', 'jpg', 'png', 'svg', 'tif', 'tiff', 'webp']);

async function cached(output, source, digest, configHash) {
  try {
    const report = await readJson(path.join(output, 'conversion-report.json'));
    if (report.archivo_original !== source || report.sha256 !== digest ||
        report.version_xberg !== XBERG_VERSION || report.version_2md !== APP_VERSION ||
        report.configuracion_hash !== configHash || report.version_cache !== 3 ||
        !['completado', 'completado_con_advertencias'].includes(report.estado) ||
        !report.archivos || !Object.keys(report.archivos).length ||
        !Array.isArray(report.advertencias) || !report.advertencias.every(item => typeof item === 'string')) return null;
    for (const [file, hash] of Object.entries(report.archivos)) {
      if (await fileHash(await confined(output, file)) !== hash) return null;
    }
    if (!Object.hasOwn(report.archivos, report.markdown)) return null;
    return { markdown: await confined(output, report.markdown), warnings: report.advertencias,
      retryable: Boolean(report.errores_ia), cached: true };
  } catch (error) {
    if (error instanceof SyntaxError || ['ENOENT', 'ENOTDIR'].includes(error.code)) return null;
    throw new Error(`No se puede validar la salida existente: ${error.message}`);
  }
}

export async function convertDocument(input, destination, { signal, variant = '' } = {}) {
  const started = performance.now();
  const source = await realpath(input);
  destination = await realpath(destination);
  if (!supported(source) || !(await stat(source)).isFile()) throw new Error('Selecciona un PDF o DOCX existente.');
  if (!(await stat(destination)).isDirectory()) throw new Error('La carpeta de destino no existe.');
  signal?.throwIfAborted();
  const before = await stat(source);
  const digest = await fileHash(source, signal);
  const unchanged = async () => {
    const after = await stat(source);
    if (before.size !== after.size || before.mtimeMs !== after.mtimeMs)
      throw new Error('El documento original cambió durante la conversión.');
  };
  await unchanged();
  const configHash = sha256(`node-v3:${APP_VERSION}:${XBERG_VERSION}:markdown:ocr=off:images=on:${variant}`);
  const stem = path.parse(source).name;
  const output = path.join(destination, `${stem}-${sha256(source.toLowerCase()).slice(0, 12)}-${digest.slice(0, 12)}-${configHash.slice(0, 12)}`);
  try {
    await stat(output);
    await confined(destination, output);
    const result = await cached(output, source, digest, configHash);
    if (result) return result;
    throw new Error(`Ya existe una salida no reutilizable: ${output}. No se sobrescribirá.`);
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  signal?.throwIfAborted();
  const result = await extract({ kind: 'uri', uri: source }, {
    useCache: false, disableOcr: true, ocrEmbeddedImages: false, outputFormat: 'markdown',
    images: { extractImages: true, injectPlaceholders: true, runOcrOnImages: false, appendOcrText: false },
    pdfOptions: { extractImages: true, ocrInlineImages: false },
    // Explicit so a changed Xberg default cannot enable layout models or follow document links.
    useLayoutForMarkdown: false, extractionTimeoutSecs: 600,
    url: { allowFileUris: false, crawl: { followDocumentUrls: false } },
  });
  signal?.throwIfAborted();
  await unchanged();
  if (!result.results?.length) throw new Error(`Xberg no pudo convertir el documento. ${(result.errors || []).map(error => error.message).join('; ')}`);
  const warnings = path.extname(source).toLowerCase() === '.pdf'
    ? ['OCR desactivado: no se extrae texto de imágenes ni de páginas escaneadas.'] : [];
  warnings.push(...(result.errors || []).map(error => `Xberg: ${error.message}`));
  const document = result.results[0];
  for (const warning of document.processingWarnings || []) {
    warnings.push(`Xberg: ${typeof warning === 'string' ? warning : warning.message || JSON.stringify(warning)}`);
  }
  const images = document.images || [];
  await mkdir(output);
  const markdown = path.join(output, `${stem}.md`);
  try {
    const references = new Map();
    let missing = 0;
    for (const [index, image] of images.entries()) {
      if (!image.data?.length) { missing++; continue; }
      const format = (image.format || '').replace(/^\./, '').toLowerCase();
      const relative = `assets/image-${String(index + 1).padStart(4, '0')}.${extensions.has(format) ? format : 'bin'}`;
      await mkdir(path.join(output, 'assets'), { recursive: true });
      await writeFile(path.join(output, relative), Buffer.from(image.data), { flag: 'wx' });
      references.set(`p${image.pageNumber || 1}_i${image.imageIndex}`, relative);
    }
    if (missing) warnings.push(`No se pudieron recuperar ${missing} imágenes del documento.`);
    const linked = new Set();
    let content = (document.content ?? '').replace(/!\[([^\]]*)\]\(embedded:([^)]+)\)/g, (_, alt, id) => {
      const relative = references.get(id);
      if (!relative) return alt;
      linked.add(relative);
      return `![${alt}](${relative})`;
    });
    // Keep extracted pictures accessible even when an extractor omits a placeholder.
    for (const relative of references.values()) {
      if (!linked.has(relative)) content += `\n\n![Imagen extraída](${relative})`;
    }
    await writeFile(markdown, content, { flag: 'wx' });
    const report = {
      archivo_original: source, sha256: digest, fecha: new Date().toISOString(),
      estado: warnings.length ? 'completado_con_advertencias' : 'completado',
      version_2md: APP_VERSION, version_xberg: XBERG_VERSION, configuracion_hash: configHash,
      version_cache: 3, modelo_ia: null, imagenes: images.length, diagramas: 0,
      diagramas_convertidos: 0, diagramas_pendientes_revision: 0, errores: [],
      advertencias: warnings, duracion_segundos: (performance.now() - started) / 1000,
      markdown: path.basename(markdown), archivos: await outputHashes(output, markdown),
    };
    await writeFile(path.join(output, 'conversion-report.json'), `${JSON.stringify(report, null, 2)}\n`, { flag: 'wx' });
  } catch (error) { throw new Error(`No se pudo exportar. Salida incompleta conservada en ${output}: ${error.message}`); }
  return { markdown, warnings, retryable: false, cached: false };
}
