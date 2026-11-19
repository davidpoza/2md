import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { documentWithImage } from './fixtures.js';

test('MCP returns readable image resources, confines paths and honors current settings', async t => {
  const root = await mkdtemp(path.join(tmpdir(), '2md-mcp-'));
  const variables = ['APPDATA', 'XDG_CONFIG_HOME'];
  const original = Object.fromEntries(variables.map(name => [name, process.env[name]]));
  for (const name of variables) process.env[name] = path.join(root, 'preferences');
  t.after(async () => {
    for (const name of variables) {
      if (original[name] === undefined) delete process.env[name];
      else process.env[name] = original[name];
    }
    await rm(root, { recursive: true, force: true });
  });
  const allowed = path.join(root, 'allowed');
  const output = path.join(root, 'output');
  await mkdir(allowed);
  await mkdir(output);
  await writeFile(path.join(allowed, 'document.pdf'), documentWithImage());
  await writeFile(path.join(root, 'private.pdf'), documentWithImage());
  const { saveSettings } = await import('../app/config.js');
  let settings = await saveSettings({ output_directory: output, mcp: { enabled: true, working_directory: allowed } });
  const { createMcpServer } = await import('../app/mcp.js');
  const server = createMcpServer();
  const client = new Client({ name: '2md-resource-check', version: '1.0.0' });
  t.after(async () => { await client.close(); await server.close(); });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);
  await client.connect(clientTransport);
  const rejected = await client.callTool({ name: 'leer_documento', arguments: { ruta: '..\\private.pdf' } });
  assert.equal(rejected.isError, true);
  const result = await client.callTool({ name: 'leer_documento', arguments: { ruta: 'document.pdf' } });
  assert.notEqual(result.isError, true, JSON.stringify(result.content));
  const document = result.structuredContent;
  assert.match(document.markdown, /Local document/);
  assert.ok(document.imagenes.length > 0);
  const image = document.imagenes[0];
  assert.ok(document.markdown.includes(image.uri));
  assert.ok(result.content.some(item => item.type === 'resource_link' && item.uri === image.uri));
  const resource = await client.readResource({ uri: image.uri });
  assert.ok(Buffer.from(resource.contents[0].blob, 'base64').length > 0);
  assert.match(resource.contents[0].mimeType, /^image\//);
  const reused = await client.callTool({ name: 'leer_documento', arguments: { ruta: 'document.pdf' } });
  assert.equal(reused.structuredContent.archivo_markdown, document.archivo_markdown);
  settings = await saveSettings({ ...settings, mcp: { ...settings.mcp, enabled: false } });
  await assert.rejects(client.readResource({ uri: image.uri }), /desactivado/);
  const disabled = await client.callTool({ name: 'leer_documento', arguments: { ruta: 'document.pdf' } });
  assert.equal(disabled.isError, true);
});
