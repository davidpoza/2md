import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { mkdtemp, mkdir, realpath, writeFile, rm } from 'node:fs/promises';
import { confined, documents } from '../app/files.js';
import { settingsSchema } from '../app/config.js';

test('selection preserves order, deduplicates paths and does not recurse into folders', async t => {
  const root = await realpath(await mkdtemp(path.join(tmpdir(), '2md-documents-')));
  t.after(() => rm(root, { recursive: true, force: true }));
  const first = path.join(root, 'a.PDF');
  const second = path.join(root, 'b.docx');
  await writeFile(first, '');
  await writeFile(second, '');
  await mkdir(path.join(root, 'nested'));
  await writeFile(path.join(root, 'nested', 'hidden.pdf'), '');
  await writeFile(path.join(root, 'ignored.txt'), '');
  assert.deepEqual(await documents([second, root, first]), [second, first]);
});

test('real paths cannot escape an allowed directory or use a sibling prefix', async t => {
  const root = await mkdtemp(path.join(tmpdir(), '2md-boundary-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, 'allowed'));
  await mkdir(path.join(root, 'allowed-other'));
  await writeFile(path.join(root, 'allowed-other', 'private.pdf'), '');
  await assert.rejects(confined(path.join(root, 'allowed'), path.join('..', 'allowed-other', 'private.pdf')), /fuera/);
});

test('settings default to no IA or MCP and reject credential-bearing URLs', () => {
  const settings = settingsSchema.parse({});
  assert.equal(settings.ai.enabled, false);
  assert.equal(settings.mcp.enabled, false);
  assert.throws(() => settingsSchema.parse({ ai: { base_url: 'https://user:secret@example.com/v1' } }));
  assert.throws(() => settingsSchema.parse({ network: { mode: 'manual' } }));
  assert.throws(() => settingsSchema.parse({ ai: { enabled: true } }));
});
