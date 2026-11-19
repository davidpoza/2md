import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { XBERG_VERSION } from '../app/conversion.js';

const root = new URL('../', import.meta.url);

test('every Xberg package is installed from the vendored tarballs with matching integrity', async () => {
  const lock = JSON.parse(await readFile(new URL('package-lock.json', root), 'utf8'));
  const packages = Object.entries(lock.packages).filter(([name]) => name.startsWith('node_modules/@xberg-io/'));
  assert.deepEqual(packages.map(([name]) => name).sort(), [
    'node_modules/@xberg-io/xberg',
    'node_modules/@xberg-io/xberg-linux-x64-gnu',
    'node_modules/@xberg-io/xberg-win32-x64-msvc',
  ]);
  for (const [name, entry] of packages) {
    assert.match(entry.resolved, /^file:vendor\/xberg\/[^/]+\.tgz$/, `${name} no se instala desde vendor/xberg.`);
    assert.equal(entry.version, XBERG_VERSION, `${name} no corresponde a XBERG_VERSION.`);
    assert.equal(entry.optionalDependencies, undefined, `${name} declara dependencias de plataforma remotas.`);
    const tarball = await readFile(new URL(entry.resolved.slice('file:'.length), root));
    assert.equal(`sha512-${createHash('sha512').update(tarball).digest('base64')}`, entry.integrity, `${name} no coincide con su integridad.`);
  }
});
