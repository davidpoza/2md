import path from 'node:path';
import { mkdir, readFile, rm } from 'node:fs/promises';
import { atomicWrite } from './config.js';
import { confined, outputHashes, readJson, sha256 } from './files.js';

const pendingBlock = (index, code) => `\n\n<!-- 2MD:mermaid-pendiente:${index} -->\n> **Diagrama generado por IA: pendiente de revisión.**\n\n\`\`\`mermaid\n${code}\n\`\`\`\n<!-- /2MD:mermaid-pendiente:${index} -->`;
const acceptedBlock = code => `\n\n\`\`\`mermaid\n${code}\n\`\`\``;
export async function pictureReferences(markdown) {
  const text = await readFile(markdown, 'utf8');
  const root = path.dirname(markdown);
  const result = [];
  let offset = 0;
  let fence = null;
  for (const line of text.match(/[^\n]*\n|[^\n]+$/g) || []) {
    const marker = /^ {0,3}(`{3,}|~{3,})([^\r\n]*)/.exec(line);
    if (fence) {
      if (marker && marker[1][0] === fence[0] && marker[1].length >= fence.length && !marker[2].trim()) fence = null;
    } else if (marker) { fence = marker[1]; }
    else for (const match of line.matchAll(/!\[[^\]\n]*\]\(([^)\n]+)\)/g)) {
      if (/^[a-z][a-z\d+.-]*:|^[/\\]{2}|[?#]/i.test(match[1])) continue;
      const relative = decodeURIComponent(match[1]);
      if (!relative.replaceAll('\\', '/').startsWith('assets/')) continue;
      const image = await confined(path.join(root, 'assets'), path.resolve(root, relative));
      const start = offset + match.index;
      const end = start + match[0].length;
      const index = result.length + 1;
      let stored = null;
      try {
        const code = (await readFile(await confined(root, `diagrams/diagram-${String(index).padStart(3, '0')}.mmd`), 'utf8')).trim();
        if (text.slice(end).startsWith(pendingBlock(index, code))) stored = { code, pending: true };
        else if (text.slice(end).startsWith(acceptedBlock(code))) stored = { code, pending: false };
      } catch (error) { if (error.code !== 'ENOENT') throw error; }
      result.push({ image, index, start, end, context: text.slice(Math.max(0, start - 1500), end + 1500), stored, revision: sha256(text) });
    }
    offset += line.length;
  }
  return result;
}

export async function storeDiagram(markdown, reference, input, model, pending = false) {
  const code = input.trim();
  if (!code || code.includes('```')) throw new Error('Código Mermaid no válido.');
  const text = await readFile(markdown, 'utf8');
  const current = (await pictureReferences(markdown))[reference.index - 1];
  if (!current || reference.revision !== sha256(text) || current.image !== reference.image)
    throw new Error('El Markdown ha cambiado; vuelve a abrir la revisión.');
  const root = path.dirname(markdown);
  const reportPath = path.join(root, 'conversion-report.json');
  const report = await readJson(reportPath);
  await mkdir(path.join(root, 'diagrams'), { recursive: true });
  const diagrams = await confined(root, 'diagrams');
  const file = path.join(diagrams, `diagram-${String(reference.index).padStart(3, '0')}.mmd`);
  const previous = current.stored;
  if (pending && previous) throw new Error('Ya existe un diagrama para esta imagen.');
  const old = previous ? previous.pending ? pendingBlock(current.index, previous.code) : acceptedBlock(previous.code) : '';
  const block = pending ? pendingBlock(current.index, code) : acceptedBlock(code);
  let written = false;
  try {
    if (previous) await atomicWrite(await confined(root, file), `${code}\n`);
    else {
      const { writeFile } = await import('node:fs/promises');
      await writeFile(file, `${code}\n`, { flag: 'wx' });
    }
    written = true;
    await atomicWrite(markdown, text.slice(0, current.end) + block + text.slice(current.end + old.length));
    if (!previous) { report.diagramas++; report.diagramas_convertidos++; }
    report.diagramas_pendientes_revision += pending ? 1 : previous?.pending ? -1 : 0;
    if (model) report.modelo_ia = model;
    report.archivos = await outputHashes(root, markdown);
    await atomicWrite(reportPath, `${JSON.stringify(report, null, 2)}\n`);
  } catch (error) {
    if (written) {
      try {
        await atomicWrite(markdown, text);
        if (previous) await atomicWrite(file, `${previous.code}\n`);
        else await rm(file);
      } catch { throw new Error('La revisión falló y no pudo restaurarse completamente; comprueba la salida.'); }
    }
    throw error;
  }
}
