import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { readFile, stat } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { loadSettings, saveSettings, settingsSchema } from './config.js';
import { documents, mimeType } from './files.js';
import { Batch } from './batch.js';
import { consentText, proposeDiagram, checkConnection } from './ai.js';
import { setSecret } from './credentials.js';
import { pictureReferences, storeDiagram } from './review.js';
import { renderMermaid } from './mermaid.js';

const directory = path.dirname(fileURLToPath(import.meta.url));
const mcp = process.argv.includes('--mcp');
app.commandLine.appendSwitch('disable-background-networking');
let window;
let settings;
const validations = new Map();
let reviewDocument = null;
const notify = event => { if (window && !window.isDestroyed()) window.webContents.send('2md-event', event); };
const batch = new Batch(notify, renderMermaid);
let interaction = false;
const activity = message => notify({ type: 'activity', message });

async function confirm(message) {
  const result = await dialog.showMessageBox(window, {
    type: 'warning', message, buttons: ['Cancelar', 'Autorizar'], defaultId: 0, cancelId: 0,
  });
  return result.response === 1;
}
function idle() {
  if (batch.running || interaction) throw new Error('Espera a que termine la operación en curso.');
}
async function select(properties, filters) {
  const result = await dialog.showOpenDialog(window, { properties, filters });
  return result.canceled ? [] : result.filePaths;
}
async function referenceFor(id, index, revision) {
  if (reviewDocument !== id) throw new Error('Vuelve a abrir la revisión de este documento.');
  const row = batch.rows.find(item => item.id === id);
  if (!row?.outcome) throw new Error('Selecciona un documento convertido.');
  const references = await pictureReferences(row.outcome.markdown);
  const reference = references.find(item => item.index === index);
  if (!reference || reference.revision !== revision) throw new Error('El Markdown ha cambiado; vuelve a abrir la revisión.');
  return { row, reference };
}
async function dispatch(method, ...args) {
  switch (method) {
    case 'state': return { settings, rows: batch.rows, running: batch.running };
    case 'choose-files': batch.add(await documents(await select(['openFile', 'multiSelections'], [{ name: 'Documentos', extensions: ['pdf', 'docx'] }]))); return;
    case 'choose-folder': batch.add(await documents(await select(['openDirectory']))); return;
    case 'add': {
      if (!Array.isArray(args[0]) || !args[0].every(value => typeof value === 'string')) throw new Error('Rutas no válidas.');
      batch.add(await documents(args[0])); return;
    }
    case 'choose-destination': {
      idle();
      const [folder] = await select(['openDirectory']);
      if (folder) settings = await saveSettings({ ...settings, output_directory: folder });
      return settings.output_directory;
    }
    case 'open-destination': {
      const destination = settings.output_directory;
      if (!destination) throw new Error('Selecciona primero una carpeta de destino.');
      if (!path.isAbsolute(destination) || !(await stat(destination)).isDirectory())
        throw new Error('La carpeta de destino debe ser un directorio absoluto existente.');
      const error = await shell.openPath(destination);
      if (error) throw new Error(`No se pudo abrir la carpeta de destino: ${error}`);
      return;
    }
    case 'choose-directory': return (await select(['openDirectory']))[0];
    case 'choose-ca': return (await select(['openFile'], [{ name: 'Certificados', extensions: ['pem', 'crt'] }]))[0];
    case 'save-settings': {
      idle();
      const parsed = settingsSchema.parse(args[0]);
      const secrets = args[1] || {};
      if (parsed.mcp.enabled && !(await stat(parsed.mcp.working_directory)).isDirectory()) throw new Error('El directorio MCP no existe.');
      if (Object.keys(secrets).some(name => !['api', 'proxy'].includes(name)) ||
          Object.values(secrets).some(value => typeof value !== 'string')) throw new Error('Credenciales no válidas.');
      for (const [name, value] of Object.entries(secrets)) if (value) setSecret(name, value);
      settings = await saveSettings(parsed);
      return settings;
    }
    case 'check-connection': {
      idle();
      if (!['network', 'text', 'vision'].includes(args[0])) throw new Error('Prueba desconocida.');
      interaction = true;
      try {
        if (!await confirm(`Prueba explícita de conexión.\n${consentText(settings)}${args[0] === 'vision' ? '\nSe enviará una imagen sintética de un píxel, no un documento.' : ''}`)) return 'Prueba cancelada.';
        return await checkConnection(settings, args[0], activity);
      } finally { interaction = false; }
    }
    case 'start': {
      idle();
      if (typeof args[0] !== 'boolean' || typeof args[1] !== 'boolean') throw new Error('Opciones de lote no válidas.');
      interaction = true;
      let automatic;
      try {
        automatic = args[0];
        if (automatic && (!settings.ai.enabled || !await confirm(`Análisis automático de este lote.\n${consentText(settings)}`))) {
          if (!settings.ai.enabled) throw new Error('Activa y configura la IA primero.');
          return false;
        }
      } finally { interaction = false; }
      // The handler returns immediately so cancellation remains available.
      void batch.run(structuredClone(settings), automatic, args[1]).catch(error => activity(error.message));
      return true;
    }
    case 'cancel': batch.cancel(); return;
    case 'fullscreen':
      if (typeof args[0] !== 'boolean') throw new Error('Opción de pantalla completa no válida.');
      window.setFullScreen(args[0]);
      return;
    case 'review': {
      idle();
      interaction = true;
      try {
        const row = batch.rows.find(item => item.id === args[0]);
        if (!row?.outcome) throw new Error('Selecciona un documento convertido.');
        const references = await pictureReferences(row.outcome.markdown);
        const pictures = await Promise.all(references.map(async reference => ({
          index: reference.index, name: path.basename(reference.image),
          revision: reference.revision, stored: reference.stored,
          image: `data:${mimeType(reference.image)};base64,${(await readFile(reference.image)).toString('base64')}`,
        })));
        validations.clear();
        reviewDocument = row.id;
        return pictures;
      } finally { interaction = false; }
    }
    case 'close-review':
      idle();
      validations.clear();
      reviewDocument = null;
      return;
    case 'propose': {
      idle();
      interaction = true;
      try {
        const { reference } = await referenceFor(...args);
        if (!settings.ai.enabled) throw new Error('La IA está desactivada.');
        if (!await confirm(consentText(settings))) return null;
        const proposal = await proposeDiagram(reference, settings, undefined, activity);
        return { ...proposal, model: proposal.fiable ? settings.ai.model : null };
      } finally { interaction = false; }
    }
    case 'validate': {
      idle();
      interaction = true;
      try {
        const { row, reference } = await referenceFor(...args);
        const code = args[3];
        const model = args[4] ?? null;
        if (model !== null && (typeof model !== 'string' || model.length > 1024))
          throw new Error('Modelo de la propuesta no válido.');
        const svg = await renderMermaid(code);
        const token = randomUUID();
        for (const [previousToken, validation] of validations) {
          if (validation.markdown === row.outcome.markdown && validation.reference.index === reference.index)
            validations.delete(previousToken);
        }
        validations.set(token, { markdown: row.outcome.markdown, reference, code, model });
        return { token, svg };
      } finally { interaction = false; }
    }
    case 'accept': {
      idle();
      const validation = validations.get(args[0]);
      if (!validation) throw new Error('Valida de nuevo el Mermaid después de editarlo.');
      interaction = true;
      try {
        if (!await confirm('Confirma que has comparado visualmente el diagrama renderizado con la imagen original y que representa fielmente su contenido. Se conservará la imagen original.')) return false;
        const revision = validation.reference.revision;
        await storeDiagram(validation.markdown, validation.reference, validation.code, validation.model);
        const references = await pictureReferences(validation.markdown);
        for (const [token, saved] of validations) {
          const current = references.find(reference => reference.index === saved.reference.index);
          if (saved.markdown === validation.markdown && current?.image === saved.reference.image &&
              saved.reference.revision === revision) {
            saved.reference = current;
          } else validations.delete(token);
        }
        return references.map(reference => ({ index: reference.index, revision: reference.revision, stored: reference.stored }));
      } finally { interaction = false; }
    }
    default: throw new Error('Operación no disponible.');
  }
}

async function startApplication() {
  if (mcp) {
    try {
      console.log = (...args) => console.error(...args);
      const { startMcp } = await import('./mcp.js');
      await startMcp();
    } catch (error) { console.error(error.message); app.exit(1); }
  } else {
    try {
      settings = await loadSettings();
      window = new BrowserWindow({
        width: 1100, height: 800, minWidth: 850, minHeight: 650, title: '2MD',
        webPreferences: { preload: path.join(directory, 'preload.cjs'), nodeIntegration: false, contextIsolation: true, sandbox: true },
      });
      window.setMenu(null);
      window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
      window.webContents.on('will-navigate', event => event.preventDefault());
      window.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
      window.webContents.session.webRequest.onBeforeRequest((details, callback) =>
        callback({ cancel: !details.url.startsWith('file:') && !details.url.startsWith('data:') && !details.url.startsWith('blob:') }));
      ipcMain.handle('2md', async (event, method, ...args) => {
        try {
          if (event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame ||
              event.senderFrame.url !== pathToFileURL(path.join(directory, 'renderer', 'index.html')).href)
            throw new Error('Origen IPC no autorizado.');
          return { ok: true, value: await dispatch(method, ...args) };
        } catch (error) { return { ok: false, error: error.message }; }
      });
      window.on('close', event => {
        if (batch.running || interaction) { event.preventDefault(); activity('Cancela el lote y espera a que terminen las operaciones antes de cerrar.'); }
      });
      await window.loadFile(path.join(directory, 'renderer', 'index.html'));
    } catch (error) {
      dialog.showErrorBox('No se puede iniciar 2MD', error.message);
      app.exit(1);
    }
    app.on('window-all-closed', () => app.quit());
  }
}

// Electron must finish evaluating this ESM entry point before it can become ready.
app.whenReady().then(startApplication).catch(error => {
  if (mcp) console.error(error.message);
  else dialog.showErrorBox('No se puede iniciar 2MD', error.message);
  app.exit(1);
});
