import path from 'node:path';
import { createReadStream } from 'node:fs';
import { realpath, stat, readdir, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

export const sha256 = value => createHash('sha256').update(value).digest('hex');
export const supported = file => ['.pdf', '.docx'].includes(path.extname(file).toLowerCase());
export function within(root, file) {
  const relative = path.relative(root, file);
  return relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}
export async function confined(root, file) {
  root = await realpath(root);
  const resolved = await realpath(path.resolve(root, file));
  if (!within(root, resolved)) throw new Error('La ruta está fuera del directorio permitido.');
  return resolved;
}
export async function fileHash(file, signal) {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(file)) {
    signal?.throwIfAborted();
    hash.update(chunk);
  }
  return hash.digest('hex');
}
export async function documents(paths) {
  const result = [];
  const seen = new Set();
  for (const input of paths) {
    const info = await stat(input);
    const entries = info.isDirectory()
      ? (await readdir(input)).sort((a, b) => a.localeCompare(b)).map(name => path.join(input, name))
      : [input];
    for (const entry of entries) {
      if (!supported(entry) || !(await stat(entry)).isFile()) continue;
      const file = await realpath(entry);
      if (!seen.has(file.toLowerCase())) {
        seen.add(file.toLowerCase());
        result.push(file);
      }
    }
  }
  return result;
}
export async function outputHashes(root, markdown) {
  const files = [markdown];
  for (const folder of ['assets', 'diagrams']) {
    let entries;
    try { entries = await readdir(path.join(root, folder), { recursive: true, withFileTypes: true }); }
    catch (error) { if (error.code === 'ENOENT') continue; throw error; }
    for (const entry of entries) {
      if (entry.isSymbolicLink()) throw new Error('No se admiten enlaces en los resultados.');
      if (entry.isFile()) files.push(await confined(root, path.join(entry.parentPath, entry.name)));
    }
  }
  const hashes = {};
  for (const file of files) hashes[path.relative(root, file).split(path.sep).join('/')] = await fileHash(file);
  return hashes;
}
export const readJson = async file => JSON.parse(await readFile(file, 'utf8'));
export function mimeType(file) {
  return ({ '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
    '.gif': 'image/gif', '.svg': 'image/svg+xml', '.bmp': 'image/bmp', '.tif': 'image/tiff',
    '.tiff': 'image/tiff' })[path.extname(file).toLowerCase()] || 'application/octet-stream';
}
