import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { pictureReferences, storeDiagram } from '../app/review.js';
import { fileHash } from '../app/files.js';
import fs from 'node:fs';
import { syncBuiltinESMExports } from 'node:module';

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
test('AI context excludes pending and accepted diagrams, including long previous proposals', async t => {
  const { root, markdown } = await fixture(t);
  await writeFile(path.join(root, 'assets', 'second.png'), 'second-image');
  await writeFile(markdown, 'Primera sección\n![Primera](assets/image.png)\n\nSegunda sección\n![Segunda](assets/second.png)\n\nTexto final\n');
  const previous = `flowchart LR\n${'PREVIOUS_NODE --> OTHER_NODE\n'.repeat(150)}`;
  const current = 'sequenceDiagram\nCURRENT_SENDER->>CURRENT_RECEIVER: Previous proposal';
  await storeDiagram(markdown, (await pictureReferences(markdown))[0], previous, 'model', true);
  await storeDiagram(markdown, (await pictureReferences(markdown))[1], current, 'model');
  const text = await readFile(markdown, 'utf8');
  const references = await pictureReferences(markdown);
  for (const reference of references) {
    assert.doesNotMatch(reference.context, /PREVIOUS_NODE|OTHER_NODE|CURRENT_SENDER|CURRENT_RECEIVER|```|mermaid-pendiente|assets\//);
  }
  assert.match(references[0].context, /Primera sección/);
  assert.match(references[1].context, /Segunda sección/);
  assert.match(references[1].context, /Texto final/);
  assert.equal(references[1].image, await fs.promises.realpath(path.join(root, 'assets', 'second.png')));
  assert.equal(references[0].stored.pending, true);
  assert.equal(references[0].stored.code, previous.trim());
  assert.equal(references[1].stored.code, current);
  assert.equal(text.slice(references[1].start, references[1].end), '![Segunda](assets/second.png)');
});
test('AI context removes whole code fences before truncating and does not include other image references', async t => {
  const { markdown } = await fixture(t);
  await writeFile(markdown, [
    '```mermaid',
    'flowchart LR',
    'OLD_BEFORE --> OLD_AFTER\n'.repeat(150),
    '![Not an image](assets/absent.png)',
    '```',
    'Título de la imagen seleccionada',
    '![Imagen](assets/image.png)',
    '',
    'Explicación de la imagen seleccionada',
    '~~~~mermaid',
    'sequenceDiagram',
    'UNRELATED_A->>UNRELATED_B: other diagram\n'.repeat(150),
    '~~~~',
    '![Otra](https://example.invalid/other.png)',
    'Texto posterior',
  ].join('\n'));
  const [reference] = await pictureReferences(markdown);
  assert.match(reference.context, /Título de la imagen seleccionada/);
  assert.match(reference.context, /Explicación de la imagen seleccionada/);
  assert.match(reference.context, /Texto posterior/);
  assert.doesNotMatch(reference.context, /OLD_BEFORE|OLD_AFTER|UNRELATED_A|UNRELATED_B|Not an image|https:|```|~~~~/);
  assert.equal(reference.stored, null);
});
test('manual review overwrites an existing unlinked Mermaid destination', async t => {
  const { root, markdown } = await fixture(t);
  await mkdir(path.join(root, 'diagrams'));
  const destination = path.join(root, 'diagrams', 'diagram-001.mmd');
  await writeFile(destination, 'previous destination\n');
  const [reference] = await pictureReferences(markdown);
  await storeDiagram(markdown, reference, 'flowchart LR\nA --> B', null);
  assert.equal(await readFile(destination, 'utf8'), 'flowchart LR\nA --> B\n');
  assert.equal(await readFile(path.join(root, 'assets', 'image.png'), 'utf8'), 'original-image');
  assert.equal((await readFile(markdown, 'utf8')).match(/```mermaid/g).length, 1);
});
test('updating an accepted diagram replaces the Markdown block even if its sidecar was changed', async t => {
  const { root, markdown } = await fixture(t);
  await storeDiagram(markdown, (await pictureReferences(markdown))[0], 'flowchart LR\nA --> B', null);
  const destination = path.join(root, 'diagrams', 'diagram-001.mmd');
  await writeFile(destination, 'outdated sidecar\n');
  await storeDiagram(markdown, (await pictureReferences(markdown))[0], 'flowchart LR\nA --> C', null);
  const text = await readFile(markdown, 'utf8');
  assert.equal(text.match(/```mermaid/g).length, 1);
  assert.doesNotMatch(text, /A --> B/);
  assert.match(text, /A --> C/);
  assert.equal(await readFile(destination, 'utf8'), 'flowchart LR\nA --> C\n');
  const report = JSON.parse(await readFile(path.join(root, 'conversion-report.json'), 'utf8'));
  assert.equal(report.diagramas, 1);
  assert.equal(report.archivos['diagrams/diagram-001.mmd'], await fileHash(destination));
});
test('an automatic proposal cannot overwrite an existing destination', async t => {
  const { root, markdown } = await fixture(t);
  await mkdir(path.join(root, 'diagrams'));
  const destination = path.join(root, 'diagrams', 'diagram-001.mmd');
  await writeFile(destination, 'keep this diagram\n');
  const [reference] = await pictureReferences(markdown);
  await assert.rejects(storeDiagram(markdown, reference, 'flowchart LR\nA --> B', null, true), /Ya existe/);
  assert.equal(await readFile(destination, 'utf8'), 'keep this diagram\n');
});
test('a failed update restores the previous destination bytes, Markdown and report', async t => {
  const { root, markdown } = await fixture(t);
  await mkdir(path.join(root, 'diagrams'));
  const destination = path.join(root, 'diagrams', 'diagram-001.mmd');
  const report = path.join(root, 'conversion-report.json');
  const previous = Buffer.from('original destination\r\n');
  await writeFile(destination, previous);
  const originalMarkdown = await readFile(markdown, 'utf8');
  const originalReport = await readFile(report, 'utf8');
  const rename = fs.promises.rename;
  const mocked = t.mock.method(fs.promises, 'rename', async (source, target) => {
    if (target === report) throw Object.assign(new Error('Report write failed'), { code: 'EIO' });
    return rename(source, target);
  });
  syncBuiltinESMExports();
  t.after(() => { mocked.mock.restore(); syncBuiltinESMExports(); });
  await assert.rejects(storeDiagram(markdown, (await pictureReferences(markdown))[0], 'flowchart LR\nA --> B', null), /Report write failed/);
  assert.deepEqual(await readFile(destination), previous);
  assert.equal(await readFile(markdown, 'utf8'), originalMarkdown);
  assert.equal(await readFile(report, 'utf8'), originalReport);
});
