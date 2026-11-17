const api = window.twomd;
const $ = id => document.getElementById(id);
let settings;
let rows = [];
let selected = null;
let pictures = [];
let validation = null;
let uiBusy = false;
let displayedPicture = null;
let fullscreen = false;
const drafts = new Map();

function log(message) {
  $('activity').value += `${new Date().toLocaleTimeString()} ${message}\n`;
  $('activity').scrollTop = $('activity').scrollHeight;
}
async function perform(operation) {
  if (uiBusy) return;
  uiBusy = true;
  $('pictures').disabled = true;
  $('mermaid-code').readOnly = true;
  try { return await operation(); }
  catch (error) { log(error.message); window.alert(error.message); }
  finally {
    uiBusy = false;
    $('pictures').disabled = false;
    $('mermaid-code').readOnly = false;
  }
}
function button(id, operation) { $(id).addEventListener('click', () => perform(operation)); }
function drawRows(running) {
  $('documents').replaceChildren();
  for (const row of rows) {
    const tr = document.createElement('tr');
    const radioCell = document.createElement('td');
    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'document';
    radio.checked = selected === row.id;
    radio.setAttribute('aria-label', `Seleccionar ${row.source}`);
    radio.addEventListener('change', () => { selected = row.id; });
    radioCell.append(radio);
    tr.append(radioCell);
    for (const text of [row.source, row.state, `${row.progress} %`]) {
      const td = document.createElement('td');
      td.textContent = text;
      tr.append(td);
    }
    $('documents').append(tr);
  }
  for (const id of ['start', 'retry', 'review', 'settings', 'choose-destination', 'automatic']) $(id).disabled = running;
  $('cancel').disabled = !running;
}
api.onEvent(event => {
  if (event.type === 'rows') { rows = event.rows; drawRows(event.running); }
  if (event.type === 'activity') log(event.message);
  if (event.type === 'progress') { $('progress').max = event.total; $('progress').value = event.done; }
});

button('files', () => api.chooseFiles());
button('folder', () => api.chooseFolder());
button('choose-destination', async () => {
  settings.output_directory = await api.chooseDestination();
  $('destination').textContent = settings.output_directory;
});
button('start', () => api.start($('automatic').checked, false));
button('retry', () => api.start($('automatic').checked, true));
button('cancel', () => api.cancel());
for (const name of ['dragenter', 'dragover', 'drop']) {
  document.addEventListener(name, event => {
    event.preventDefault();
    if (name === 'drop') void perform(() => api.addDropped(Array.from(event.dataTransfer.files)));
  });
}

const fields = [
  ['General', [
    ['document_concurrency', 'Documentos simultáneos', 'number', 1, 8],
  ]],
  ['Inteligencia artificial', [
    ['ai.enabled', 'Activar IA', 'checkbox'],
    ['ai.base_url', 'URL del endpoint', 'text'],
    ['ai.model', 'Modelo', 'text'],
    ['ai.timeout', 'Tiempo de espera (s)', 'number', 1, 600],
    ['ai.max_retries', 'Reintentos', 'number', 0, 10],
    ['ai.concurrency', 'Solicitudes simultáneas', 'number', 1, 8],
    ['ai.temperature', 'Temperatura (opcional)', 'number', 0, 2, '0.1'],
    ['ai.max_tokens', 'Tokens (opcional)', 'number', 1, 1000000],
  ]],
  ['Red y proxy', [
    ['network.mode', 'Modo de proxy', ['system', 'none', 'manual']],
    ['network.proxy_scheme', 'Protocolo del proxy', ['http', 'https']],
    ['network.proxy_host', 'Servidor proxy', 'text'],
    ['network.proxy_port', 'Puerto', 'number', 1, 65535],
    ['network.proxy_user', 'Usuario proxy (Basic)', 'text'],
    ['network.proxy_exclusions', 'Exclusiones separadas por comas', 'text'],
    ['network.ca_bundle', 'Archivo CA (vacío: almacén del sistema)', 'ca'],
  ]],
  ['MCP local', [
    ['mcp.enabled', 'Activar MCP por stdio', 'checkbox'],
    ['mcp.working_directory', 'Directorio permitido (incluye subcarpetas)', 'directory'],
  ]],
];
const get = (object, key) => key.split('.').reduce((value, part) => value[part], object);
function set(object, key, value) {
  const parts = key.split('.');
  const last = parts.pop();
  parts.reduce((target, part) => target[part], object)[last] = value;
}
function buildSettings() {
  $('settings-fields').replaceChildren();
  for (const [title, definitions] of fields) {
    const group = document.createElement('fieldset');
    const legend = document.createElement('legend');
    legend.textContent = title;
    group.append(legend);
    for (const [key, text, type, min, max, step] of definitions) {
      const label = document.createElement('label');
      label.textContent = text;
      const field = document.createElement(Array.isArray(type) ? 'select' : 'input');
      field.id = key;
      if (Array.isArray(type)) {
        for (const value of type) {
          const option = document.createElement('option');
          option.value = value;
          option.textContent = ({ system: 'Sistema / entorno', none: 'Sin proxy', manual: 'Proxy manual' })[value] || value;
          field.append(option);
        }
      } else {
        field.type = ['ca', 'directory'].includes(type) ? 'text' : type;
        if (min !== undefined) { field.min = min; field.max = max; field.step = step || '1'; }
      }
      if (type === 'checkbox') field.checked = get(settings, key);
      else field.value = get(settings, key) ?? '';
      label.append(field);
      if (['ca', 'directory'].includes(type)) {
        const choose = document.createElement('button');
        choose.type = 'button';
        choose.textContent = 'Seleccionar';
        choose.addEventListener('click', () => perform(async () => {
          const value = await (type === 'ca' ? api.chooseCa() : api.chooseDirectory());
          if (value) field.value = value;
        }));
        label.append(choose);
      }
      group.append(label);
    }
    $('settings-fields').append(group);
  }
}
button('settings', async () => {
  buildSettings();
  $('api-key').value = '';
  $('proxy-password').value = '';
  $('show-secrets').checked = false;
  $('api-key').type = 'password';
  $('proxy-password').type = 'password';
  $('settings-dialog').showModal();
});
button('close-settings', async () => {
  $('api-key').value = '';
  $('proxy-password').value = '';
  $('settings-dialog').close();
});
$('settings-dialog').addEventListener('close', () => { $('api-key').value = ''; $('proxy-password').value = ''; });
$('show-secrets').addEventListener('change', () => {
  for (const id of ['api-key', 'proxy-password']) $(id).type = $('show-secrets').checked ? 'text' : 'password';
});
$('settings-form').addEventListener('submit', event => {
  event.preventDefault();
  void perform(async () => {
    const value = structuredClone(settings);
    for (const [, definitions] of fields) for (const [key, , type] of definitions) {
      const field = $(key);
      set(value, key, type === 'checkbox' ? field.checked : type === 'number'
        ? field.value === '' ? null : Number(field.value) : field.value.trim());
    }
    settings = await api.saveSettings(value, { api: $('api-key').value, proxy: $('proxy-password').value });
    $('settings-dialog').close();
    log('Configuración guardada.');
  });
});
for (const kind of ['network', 'text', 'vision']) button(`check-${kind}`, async () => {
  const result = await api.checkConnection(kind);
  log(result);
  window.alert(result);
});

function clearValidation() {
  validation = null;
  $('accept').disabled = true;
  $('preview').removeAttribute('src');
}
function currentPicture() { return pictures[Number($('pictures').value)]; }
function showPicture() {
  if (displayedPicture !== null) drafts.set(displayedPicture, $('mermaid-code').value);
  clearValidation();
  const picture = currentPicture();
  displayedPicture = picture.index;
  $('original').src = picture.image;
  $('mermaid-code').value = drafts.get(picture.index) ?? picture.stored?.code ?? '';
  $('diagram-status').textContent = picture.stored ? picture.stored.pending ? 'Pendiente de revisión humana' : 'Aceptado anteriormente' : 'Sin diagrama';
}
async function loadReview() {
  displayedPicture = null;
  drafts.clear();
  pictures = await api.review(selected);
  if (!pictures.length) throw new Error('El documento no contiene imágenes exportadas.');
  $('pictures').replaceChildren();
  pictures.forEach((picture, index) => {
    const option = document.createElement('option');
    option.value = index;
    option.textContent = `${picture.index}${picture.stored?.pending ? ' · pendiente' : ''}`;
    $('pictures').append(option);
  });
  showPicture();
}
button('review', async () => { await loadReview(); $('review-dialog').showModal(); });
button('fullscreen', async () => { fullscreen = !fullscreen; await api.fullscreen(fullscreen); });
button('close-review', async () => { clearValidation(); $('review-dialog').close(); });
$('review-dialog').addEventListener('cancel', event => { if (uiBusy) event.preventDefault(); });
$('review-dialog').addEventListener('close', () => {
  if (fullscreen) {
    fullscreen = false;
    void api.fullscreen(false).catch(error => log(error.message));
  }
});
$('pictures').addEventListener('change', showPicture);
$('mermaid-code').addEventListener('input', clearValidation);
$('zoom').addEventListener('input', () => {
  for (const id of ['original', 'preview']) $(id).style.width = `${$('zoom').value}%`;
});
button('propose', async () => {
  const picture = currentPicture();
  const proposal = await api.propose(selected, picture.index, picture.revision);
  if (!proposal) return;
  clearValidation();
  if (proposal.fiable && proposal.mermaid) $('mermaid-code').value = proposal.mermaid;
  $('diagram-status').textContent = `${proposal.categoria}: ${proposal.motivo || (proposal.fiable ? 'Propuesta pendiente de validación y revisión' : 'Sin propuesta fiable')}`;
});
button('validate', async () => {
  clearValidation();
  const picture = currentPicture();
  const code = $('mermaid-code').value;
  const result = await api.validate(selected, picture.index, picture.revision, code);
  if ($('mermaid-code').value !== code || currentPicture() !== picture) return;
  validation = result.token;
  const bytes = new TextEncoder().encode(result.svg);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  $('preview').src = `data:image/svg+xml;base64,${btoa(binary)}`;
  $('accept').disabled = false;
  $('diagram-status').textContent = 'Válido técnicamente. Compara visualmente antes de aceptar.';
});
button('accept', async () => {
  if (!validation) throw new Error('Valida de nuevo el código Mermaid.');
  if (await api.accept(validation)) {
    log('Diagrama aceptado; imagen original conservada.');
    await loadReview();
  }
});

try {
  const initial = await api.state();
  settings = initial.settings;
  rows = initial.rows;
  $('destination').textContent = settings.output_directory;
  drawRows(initial.running);
  log('Añade documentos y selecciona una carpeta de destino.');
} catch (error) { log(error.message); window.alert(error.message); }
