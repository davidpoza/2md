import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import net from 'node:net';
import { tmpdir } from 'node:os';
import { execFile, spawn, spawnSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, readlinkSync } from 'node:fs';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { documentWithImage, wordDocumentWithImage } from './fixtures.js';

const child = fileURLToPath(new URL('./network-child.js', import.meta.url));

// Accepts any connection and records it; proxies and model hubs are pointed here.
async function trap(t) {
  const hits = [];
  const server = net.createServer(socket => {
    hits.push(`${socket.remoteAddress}:${socket.remotePort}`);
    socket.once('data', data => { hits[hits.length - 1] += ` ${data.toString('latin1').split('\r\n')[0]}`; });
    socket.destroy();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => server.close());
  return { hits, url: `http://127.0.0.1:${server.address().port}` };
}

// Internet sockets owned by a Linux process, matched by inode against its namespace tables.
function linuxSockets(pid) {
  try {
    const inodes = new Set(readdirSync(`/proc/${pid}/fd`).map(fd => {
      try { return readlinkSync(`/proc/${pid}/fd/${fd}`).match(/^socket:\[(\d+)\]$/)?.[1]; } catch { return undefined; }
    }).filter(Boolean));
    if (!inodes.size) return [];
    return ['tcp', 'tcp6', 'udp', 'udp6'].flatMap(table => readFileSync(`/proc/${pid}/net/${table}`, 'utf8')
      .trim().split('\n').slice(1).map(line => line.trim().split(/\s+/))
      .filter(fields => inodes.has(fields[9])).map(fields => `${table} ${fields[1]} -> ${fields[2]}`));
  } catch { return []; }
}

function windowsSockets(pid) {
  return new Promise(resolve => execFile('netstat', ['-ano'], { windowsHide: true }, (error, stdout) => resolve(error ? [] :
    stdout.split(/\r?\n/).map(line => line.trim().split(/\s+/))
      .filter(fields => /^(TCP|UDP)$/.test(fields[0]) && fields.at(-1) === String(pid)).map(fields => fields.join(' ')))));
}

// Polling cannot prove absence of very short connections; the trap and the offline run cover that gap.
function watch(pid) {
  const seen = new Set();
  let running = true;
  let samples = 0;
  const done = (async () => {
    while (running) {
      const sockets = process.platform === 'win32' ? await windowsSockets(pid) : linuxSockets(pid);
      for (const socket of sockets) seen.add(socket);
      samples++;
      await new Promise(resolve => setTimeout(resolve, process.platform === 'win32' ? 0 : 2));
    }
  })();
  // Resolves once a sample has started and finished after this call.
  const sampled = async () => {
    const target = samples + 2;
    while (samples < target) await new Promise(resolve => setTimeout(resolve, 5));
  };
  const stop = async () => { running = false; await done; return [...seen]; };
  return { sampled, stop };
}

function run(command, args, env) {
  return new Promise((resolve, reject) => {
    const processHandle = spawn(command, args, { env, windowsHide: true });
    const watcher = watch(processHandle.pid);
    let stdout = '';
    let stderr = '';
    processHandle.stdout.on('data', async data => {
      stdout += data;
      if (stdout.endsWith('\n')) { await watcher.sampled(); processHandle.stdin.end(); }
    });
    processHandle.stderr.on('data', data => { stderr += data; });
    processHandle.on('error', reject);
    processHandle.on('close', async code => resolve({ code, stdout, stderr, sockets: await watcher.stop() }));
  });
}

// Both documents link to `link`, so following document URLs would reach it.
async function workspace(t, link = 'https://example.com/linked.pdf') {
  const root = await mkdtemp(path.join(tmpdir(), '2md-network-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const output = path.join(root, 'output');
  await mkdir(output);
  const pdf = path.join(root, 'document.pdf');
  const docx = path.join(root, 'document.docx');
  await writeFile(pdf, documentWithImage({ link }));
  await writeFile(docx, wordDocumentWithImage({ link }));
  return { root, output, documents: [pdf, docx] };
}

function assertConverted(result) {
  assert.equal(result.code, 0, result.stderr);
  const [pdf, docx] = JSON.parse(result.stdout);
  assert.match(pdf.markdown, /Local document/);
  assert.match(docx.markdown, /Local word document/);
  for (const document of [pdf, docx]) assert.match(document.markdown, /\]\(assets\/image-0001\.png\)/);
}

test('conversion opens no network connections, even when proxies, model hubs and linked documents are reachable', async t => {
  const { hits, url } = await trap(t);
  const link = `${url}/linked.pdf`;
  const { output, documents } = await workspace(t, link);
  const env = { ...process.env, NO_PROXY: '', no_proxy: '', HF_ENDPOINT: url, HF_HUB_OFFLINE: '', HF_HUB_DISABLE_TELEMETRY: '' };
  delete env.NAPI_RS_NATIVE_LIBRARY_PATH;
  for (const name of ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']) env[name] = env[name.toLowerCase()] = url;
  const result = await run(process.execPath, [child, output, ...documents], env);
  assertConverted(result);
  // Xberg's SSRF policy rejects loopback targets before connecting, but reports the attempt as an error.
  for (const document of JSON.parse(result.stdout)) {
    assert.ok(!document.warnings.some(warning => warning.includes(link)), `Xberg intentó seguir un enlace del documento: ${document.warnings.join('; ')}`);
  }
  assert.deepEqual(hits, [], 'Xberg intentó conectarse a través del proxy, del hub de modelos o de un enlace del documento.');
  assert.deepEqual(result.sockets, [], 'El proceso de conversión abrió sockets de red.');
});

test('conversion works without any network interface', async t => {
  if (process.platform !== 'linux' || spawnSync('unshare', ['-rn', 'true']).status !== 0) {
    t.skip('Requiere Linux con espacios de nombres de usuario y red (unshare -rn).');
    return;
  }
  const { output, documents } = await workspace(t);
  const env = { ...process.env };
  delete env.NAPI_RS_NATIVE_LIBRARY_PATH;
  assertConverted(await run('unshare', ['-rn', process.execPath, child, output, ...documents], env));
});

test('conversion ignores a native library override for Xberg', async t => {
  const { root, output, documents } = await workspace(t);
  const marker = path.join(root, 'override-loaded');
  const override = path.join(root, 'override.cjs');
  await writeFile(override, `require('node:fs').writeFileSync(${JSON.stringify(marker)}, '');\nthrow new Error('override');\n`);
  const result = await run(process.execPath, [child, output, ...documents], { ...process.env, NAPI_RS_NATIVE_LIBRARY_PATH: override });
  assertConverted(result);
  assert.equal(existsSync(marker), false, 'Se cargó la biblioteca indicada por NAPI_RS_NATIVE_LIBRARY_PATH.');
});
