import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { pictureReferences, storeDiagram } from '../app/review.js';
import { fileHash } from '../app/files.js';

async function fixture(t) {
  const root = await mkdtemp(path.join(tmpdir(), '2md-review-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, 'assets'));
  await writeFile(path.join(root, 'assets', 'image.png'), 'original-image');
  const markdown = path.join(root, 'document.md');
  await writeFile(markdown, 'Contexto\n![Imagen](assets/image.png)\n\n```md\n![Ejemplo](assets/absent.png)\n```\n');
  await writeFile(path.join(root, 'conversion-report.json'), JSON.stringify({
    diagramas: 0, diagramas_convertidos: 0, diagramas_pendientes_revision: 0,
  }));
  return { root, markdown };
}
test('a pending proposal can be accepted without losing the original image or duplicating blocks', async t => {
  const { root, markdown } = await fixture(t);
  const [reference] = await pictureReferences(markdown);
  assert.equal((await pictureReferences(markdown)).length, 1);
  await storeDiagram(markdown, reference, 'flowchart LR\nA --> B', 'model', true);
  let [current] = await pictureReferences(markdown);
  assert.equal(current.stored.pending, true);
  await storeDiagram(markdown, current, 'flowchart LR\nA --> C', 'model', false);
  [current] = await pictureReferences(markdown);
  assert.equal(current.stored.pending, false);
  const text = await readFile(markdown, 'utf8');
  assert.match(text, /!\[Imagen\]\(assets\/image.png\)/);
  assert.equal((text.match(/```mermaid/g) || []).length, 1);
  assert.doesNotMatch(text, /pendiente/);
  const report = JSON.parse(await readFile(path.join(root, 'conversion-report.json'), 'utf8'));
  assert.equal(report.diagramas, 1);
  assert.equal(report.diagramas_pendientes_revision, 0);
  assert.equal(report.archivos['document.md'], await fileHash(markdown));
});
test('review refuses to apply a validation to a changed Markdown document', async t => {
  const { markdown } = await fixture(t);
  const [reference] = await pictureReferences(markdown);
  await writeFile(markdown, `${await readFile(markdown, 'utf8')}\nCambio posterior`);
  await assert.rejects(storeDiagram(markdown, reference, 'flowchart LR\nA --> B', null), /ha cambiado/);
});
test('an image reference outside assets is rejected even when it begins with assets', async t => {
  const { root, markdown } = await fixture(t);
  await writeFile(path.join(root, 'private.png'), 'not-an-asset');
  await writeFile(markdown, '![Imagen](assets/../private.png)');
  await assert.rejects(pictureReferences(markdown), /fuera/);
});
