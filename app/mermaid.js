import { BrowserWindow } from 'electron';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const directory = path.dirname(fileURLToPath(import.meta.url));
let queue = Promise.resolve();
export function checkMermaid(code) {
  if (typeof code !== 'string' || !code.trim() || code.length > 100000 || code.includes('```'))
    throw new Error('El Mermaid debe contener entre 1 y 100000 caracteres, sin delimitadores Markdown.');
  if (/%%\s*\{|^\s*---|<\/?[a-z][^>]*>|&(?:lt|gt|#0*60|#x0*3c);|\b(?:click|href)\b/i.test(code))
    throw new Error('No se admiten HTML, enlaces interactivos ni directivas de configuración en Mermaid.');
}
export function renderMermaid(code) {
  checkMermaid(code);
  const task = queue.then(async () => {
    const window = new BrowserWindow({
      show: false,
      webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true, partition: 'mermaid-offline' },
    });
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    window.webContents.on('will-navigate', event => event.preventDefault());
    window.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
    window.webContents.session.webRequest.onBeforeRequest((details, callback) =>
      callback({ cancel: !details.url.startsWith('file:') && !details.url.startsWith('data:') }));
    let timer;
    try {
      return await Promise.race([
        (async () => {
          await window.loadFile(path.join(directory, 'renderer', 'mermaid.html'));
          return await window.webContents.executeJavaScript(`window.renderDiagram(${JSON.stringify(code)})`);
        })(),
        new Promise((_, reject) => {
          timer = setTimeout(() => reject(new Error('El renderizado Mermaid superó 180 segundos.')), 180000);
        }),
      ]);
    } finally { clearTimeout(timer); if (!window.isDestroyed()) window.destroy(); }
  });
  queue = task.catch(() => undefined);
  return task;
}
