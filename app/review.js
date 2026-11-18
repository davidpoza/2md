import path from 'node:path';
import { lstat, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { atomicWrite } from './config.js';
import { confined, outputHashes, readJson, sha256 } from './files.js';

const pendingBlock = (index, code) => `\n\n<!-- 2MD:mermaid-pendiente:${index} -->\n> **Diagrama generado por IA: pendiente de revisión.**\n\n\`\`\`mermaid\n${code}\n\`\`\`\n<!-- /2MD:mermaid-pendiente:${index} -->`;
const acceptedBlock = code => `\n\n\`\`\`mermaid\n${code}\n\`\`\``;
const imageLink = /!\[[^\]\n]*\]\(([^)\n]+)\)/g;
function diagramAfter(text, index) {
  const pending = new RegExp(`^\\n\\n<!-- 2MD:mermaid-pendiente:${index} -->\\n> \\*\\*Diagrama generado por IA: pendiente de revisión\\.\\*\\*\\n\\n\`\`\`mermaid\\n([\\s\\S]*?)\\n\`\`\`\\n<!-- /2MD:mermaid-pendiente:${index} -->`).exec(text);
  const accepted = /^\n\n```mermaid\n([\s\S]*?)\n```/.exec(text);
  const match = pending || accepted;
  return match ? { code: match[1], pending: Boolean(pending), block: match[0] } : null;
}
function* proseLines(text) {
  let offset = 0;
  let fence = null;
  for (const line of text.match(/[^\n]*\n|[^\n]+$/g) || []) {
    const start = offset;
    offset += line.length;
    const marker = /^ {0,3}(`{3,}|~{3,})([^\r\n]*)/.exec(line);
    if (fence) {
      if (marker && marker[1][0] === fence[0] && marker[1].length >= fence.length && !marker[2].trim()) fence = null;
    } else if (marker) { fence = marker[1]; }
    else yield { line, start };
  }
}
function contextText(text) {
  let context = '';
  for (const { line } of proseLines(text)) {
    if (/^(?:<!-- \/?2MD:mermaid-pendiente:\d+ -->|> \*\*Diagrama generado por IA: pendiente de revisión\.\*\*)\r?\n?$/.test(line)) continue;
    context += line.replace(imageLink, '');
  }
  return context;
}
export async function pictureReferences(markdown) {
  const text = await readFile(markdown, 'utf8');
  const root = path.dirname(markdown);
  const result = [];
  for (const { line, start: offset } of proseLines(text)) {
    for (const match of line.matchAll(imageLink)) {
      if (/^[a-z][a-z\d+.-]*:|^[/\\]{2}|[?#]/i.test(match[1])) continue;
      const relative = decodeURIComponent(match[1]);
      if (!relative.replaceAll('\\', '/').startsWith('assets/')) continue;
      const image = await confined(path.join(root, 'assets'), path.resolve(root, relative));
      const start = offset + match.index;
      const end = start + match[0].length;
      const index = result.length + 1;
      const stored = diagramAfter(text.slice(end), index);
      result.push({ image, index, start, end, stored, revision: sha256(text) });
    }
  }
  for (const [position, reference] of result.entries()) {
    const previous = result[position - 1];
    const next = result[position + 1];
    const before = contextText(text.slice(previous ? previous.end + (previous.stored?.block.length || 0) : 0, reference.start));
    const after = contextText(text.slice(reference.end + (reference.stored?.block.length || 0), next?.start ?? text.length));
    reference.context = `${before.slice(-1500)}\n[Imagen seleccionada]\n${after.slice(0, 1500)}`;
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
  let previousFile = null;
  try {
    if (!(await lstat(file)).isFile()) throw new Error('El destino Mermaid debe ser un archivo regular, no un enlace.');
    previousFile = await readFile(await confined(diagrams, file));
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (pending && (previous || previousFile !== null)) throw new Error('Ya existe un diagrama para esta imagen.');
  const old = previous?.block || '';
  const block = pending ? pendingBlock(current.index, code) : acceptedBlock(code);
  let written = false;
  try {
    if (pending) await writeFile(file, `${code}\n`, { flag: 'wx' });
    else await atomicWrite(file, `${code}\n`);
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
        if (previousFile !== null) await atomicWrite(file, previousFile);
        else await rm(file);
      } catch { throw new Error('La revisión falló y no pudo restaurarse completamente; comprueba la salida.'); }
    }
    throw error;
  }
}
