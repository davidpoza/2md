import { homedir } from 'node:os';
import path from 'node:path';
import { readFile, mkdir, rename, writeFile, rm } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { isIP } from 'node:net';
import { z } from 'zod';

const validHost = value => Boolean(isIP(value)) || /^[a-z\d-]+(?:\.[a-z\d-]+)*$/i.test(value);
const host = z.string().refine(value => !value || validHost(value), 'Servidor no válido');
export const settingsSchema = z.object({
  output_directory: z.string().default(''),
  document_concurrency: z.number().int().min(1).max(8).default(2),
  ai: z.object({
    enabled: z.boolean().default(false),
    base_url: z.string().default('').refine(value => {
      if (!value) return true;
      try {
        const url = new URL(value);
        return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password && !url.search && !url.hash;
      } catch { return false; }
    }, 'URL HTTP(S) sin credenciales ni parámetros'),
    model: z.string().default(''),
    timeout: z.number().int().min(1).max(600).default(60),
    max_retries: z.number().int().min(0).max(10).default(2),
    concurrency: z.number().int().min(1).max(8).default(1),
    temperature: z.number().min(0).max(2).nullable().default(null),
    max_tokens: z.number().int().min(1).max(1000000).nullable().default(null),
  }).strict().default({}),
  network: z.object({
    mode: z.enum(['none', 'system', 'manual']).default('system'),
    proxy_scheme: z.enum(['http', 'https']).default('http'),
    proxy_host: host.default(''),
    proxy_port: z.number().int().min(1).max(65535).default(8080),
    proxy_user: z.string().default(''),
    proxy_exclusions: z.string().default('').refine(value =>
      value.split(',').every(item => !item.trim() || item.trim() === '*' || validHost(item.trim().replace(/^\./, ''))),
    'Exclusiones: nombres o direcciones IP, sin CIDR'),
    ca_bundle: z.string().default(''),
  }).strict().default({}),
  mcp: z.object({
    enabled: z.boolean().default(false),
    working_directory: z.string().default(''),
  }).strict().default({}),
}).strict().superRefine((value, context) => {
  if (value.ai.enabled && (!value.ai.base_url || !value.ai.model.trim()))
    context.addIssue({ code: 'custom', message: 'La IA requiere URL y modelo' });
  if (value.mcp.enabled && !path.isAbsolute(value.mcp.working_directory))
    context.addIssue({ code: 'custom', message: 'MCP requiere un directorio absoluto' });
  if (value.network.mode === 'manual' && !value.network.proxy_host)
    context.addIssue({ code: 'custom', message: 'Falta el servidor proxy' });
});

export const settingsPath = path.join(process.env.APPDATA || path.join(homedir(), 'AppData', 'Roaming'), '2MD', 'settings.json');

export async function atomicWrite(file, content) {
  const temporary = `${file}.${randomUUID()}.tmp`;
  try {
    await writeFile(temporary, content, { flag: 'wx' });
    for (let attempt = 0; ; attempt++) {
      try { await rename(temporary, file); break; }
      catch (error) {
        if (!['EPERM', 'EBUSY', 'EACCES'].includes(error.code) || attempt === 4) throw error;
        await new Promise(resolve => setTimeout(resolve, 100 * 2 ** attempt));
      }
    }
  } finally { await rm(temporary, { force: true }); }
}

export async function loadSettings() {
  let text;
  try { text = await readFile(settingsPath, 'utf8'); }
  catch (error) { if (error.code === 'ENOENT') return settingsSchema.parse({}); throw error; }
  const data = JSON.parse(text);
  delete data.models_directory;
  return settingsSchema.parse(data);
}

export async function saveSettings(value) {
  const settings = settingsSchema.parse(value);
  await mkdir(path.dirname(settingsPath), { recursive: true });
  await atomicWrite(settingsPath, `${JSON.stringify(settings, null, 2)}\n`);
  return settings;
}
