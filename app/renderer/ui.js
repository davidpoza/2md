import { ReviewSession } from './review-state.js';
import { ImageViewer, svgSource } from './image-viewer.js';

const api = window.twomd;
const $ = id => document.getElementById(id);
let settings;
let rows = [];
let selected = null;
let uiBusy = false;
let review = null;
let fullscreen = false;
let busyMessage = '';
const viewers = [];

function log(message) {
  $('activity').value += `${new Date().toLocaleTimeString()} ${message}\n`;
  $('activity').scrollTop = $('activity').scrollHeight;
}
async function perform(operation, message = 'Procesando...') {
  if (uiBusy) return;
  uiBusy = true;
  busyMessage = message;
  updateReviewControls();
  try { return await operation(); }
  catch (error) {
    if (review?.current) review.current.message = error.message;
    log(error.message);
    window.alert(error.message);
  }
  finally {
    uiBusy = false;
    updateReviewControls();
  }
}
function button(id, operation, message) { $(id).addEventListener('click', () => perform(operation, message)); }
function showDestination() {
  $('destination').textContent = settings.output_directory;
  $('open-destination').disabled = !settings.output_directory;
}
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
  showDestination();
});
button('open-destination', () => api.openDestination());
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
  ['general', 'General', [
    ['document_concurrency', 'Documentos simultáneos', 'number', 1, 8],
  ]],
  ['ai', 'Inteligencia artificial', [
    ['ai.enabled', 'Activar IA', 'checkbox'],
    ['ai.base_url', 'URL del endpoint', 'text'],
    ['ai.model', 'Modelo', 'text'],
    ['ai.timeout', 'Tiempo de espera (s)', 'number', 1, 600],
    ['ai.max_retries', 'Reintentos', 'number', 0, 10],
    ['ai.concurrency', 'Solicitudes simultáneas', 'number', 1, 8],
    ['ai.temperature', 'Temperatura (opcional)', 'number', 0, 2, '0.1'],
    ['ai.max_tokens', 'Tokens (opcional)', 'number', 1, 1000000],
  ]],
  ['network', 'Red y proxy', [
    ['network.mode', 'Modo de proxy', ['system', 'none', 'manual']],
    ['network.proxy_scheme', 'Protocolo del proxy', ['http', 'https']],
    ['network.proxy_host', 'Servidor proxy', 'text'],
    ['network.proxy_port', 'Puerto', 'number', 1, 65535],
    ['network.proxy_user', 'Usuario proxy (Basic)', 'text'],
    ['network.proxy_exclusions', 'Exclusiones separadas por comas', 'text'],
    ['network.ca_bundle', 'Archivo CA (vacío: almacén del sistema)', 'ca'],
  ]],
  ['mcp', 'MCP local', [
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
  for (const [section, title, definitions] of fields) {
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
      if (type === 'checkbox') {
        field.checked = get(settings, key);
        label.className = 'checkbox-label';
        label.prepend(field);
      } else {
        field.value = get(settings, key) ?? '';
        label.append(field);
      }
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
    $(`settings-${section}-fields`).replaceChildren(group);
  }
}
function activateSettingsTab(tab, focus = false) {
  for (const item of $('settings-tabs').querySelectorAll('[role="tab"]')) {
    const active = item === tab;
    item.setAttribute('aria-selected', String(active));
    item.tabIndex = active ? 0 : -1;
    $(item.getAttribute('aria-controls')).hidden = !active;
  }
  if (focus) tab.focus();
}
$('settings-tabs').addEventListener('click', event => {
  const tab = event.target.closest('[role="tab"]');
  if (tab) activateSettingsTab(tab);
});
$('settings-tabs').addEventListener('keydown', event => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  const tabs = [...$('settings-tabs').querySelectorAll('[role="tab"]')];
  const current = tabs.indexOf(event.target);
  if (current < 0) return;
  event.preventDefault();
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1
    : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
  activateSettingsTab(tabs[next], true);
});
button('settings', async () => {
  buildSettings();
  activateSettingsTab($('tab-general'));
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
  const invalid = event.currentTarget.querySelector('input:invalid, select:invalid, textarea:invalid');
  if (invalid) {
    const panel = invalid.closest('[role="tabpanel"]');
    if (panel) activateSettingsTab($('settings-tabs').querySelector(`[aria-controls="${panel.id}"]`));
    invalid.reportValidity();
    return;
  }
  void perform(async () => {
    const value = structuredClone(settings);
    for (const [, , definitions] of fields) for (const [key, , type] of definitions) {
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

const originalViewer = new ImageViewer($('original-viewer'), 'Original', () => perform(openComparison, 'Abriendo comparación ampliada...'));
const previewViewer = new ImageViewer($('preview-viewer'), 'Mermaid validado', () => perform(openComparison, 'Abriendo comparación ampliada...'));
const originalExpanded = new ImageViewer($('original-expanded'), 'Original');
const previewExpanded = new ImageViewer($('preview-expanded'), 'Mermaid validado');
viewers.push(originalViewer, previewViewer, originalExpanded, previewExpanded);

function updateReviewControls() {
  for (const id of ['review-dialog', 'viewer-dialog']) {
    const dialog = $(id);
    dialog.setAttribute('aria-busy', String(uiBusy));
    dialog.querySelector('.loading-overlay').hidden = !uiBusy || !dialog.open;
    dialog.querySelector('.loading-message').textContent = busyMessage;
  }
  for (const viewer of viewers) viewer.setDisabled(uiBusy);
  for (const button of $('pictures').querySelectorAll('button')) button.disabled = uiBusy;
  $('mermaid-code').readOnly = uiBusy || !review;
  $('close-review').disabled = uiBusy;
  $('close-viewer').disabled = uiBusy;
  $('propose').disabled = uiBusy || !review || !settings?.ai.enabled;
  $('validate').disabled = uiBusy || !review?.current.code.trim();
  $('accept').disabled = uiBusy || !review?.canAccept() || !originalViewer.ready || !previewViewer.ready;
  $('diagram-status').textContent = review?.current.message || '';
  updatePictureRows();
}
function updatePictureRows() {
  if (!review) return;
  for (const row of $('pictures').rows) {
    const index = Number(row.dataset.index);
    const status = review.status(index);
    row.setAttribute('aria-selected', String(index === review.selected));
    row.dataset.status = status === 'Aceptado' ? 'accepted' : 'pending';
    row.querySelector('button').setAttribute('aria-current', String(index === review.selected));
    row.cells[2].textContent = status;
  }
}
function drawPictures() {
  $('pictures').replaceChildren();
  for (const picture of review.pictures) {
    const row = document.createElement('tr');
    row.dataset.index = picture.index;
    const cell = document.createElement('td');
    const select = document.createElement('button');
    select.type = 'button';
    select.textContent = `Diagrama ${picture.index}`;
    select.addEventListener('click', () => navigatePicture(picture.index));
    cell.append(select);
    row.append(cell);
    for (const text of [picture.name, review.status(picture.index)]) {
      const td = document.createElement('td');
      td.textContent = text;
      row.append(td);
    }
    $('pictures').append(row);
  }
  updatePictureRows();
}
function rememberViews(expanded = false) {
  if (!review) return;
  review.current.originalView = (expanded ? originalExpanded : originalViewer).snapshot();
  review.current.previewView = (expanded ? previewExpanded : previewViewer).snapshot();
}
async function showViews(expanded = false) {
  const state = review.current;
  const preview = state.svg ? svgSource(state.svg) : null;
  const views = await Promise.allSettled([
    (expanded ? originalExpanded : originalViewer).show(review.picture.image, state.originalView),
    (expanded ? previewExpanded : previewViewer).show(preview?.source, state.previewView, preview?.dimensions),
  ]);
  const failed = views.find(view => view.status === 'rejected');
  if (failed) throw failed.reason;
}
async function selectPicture(index) {
  rememberViews();
  review.select(index);
  $('mermaid-code').value = review.current.code;
  updateReviewControls();
  await showViews();
}
async function navigatePicture(index) {
  await perform(() => selectPicture(index), 'Cargando diagrama...');
  if (review?.selected === index && !uiBusy)
    $('pictures').querySelector(`tr[data-index="${index}"] button`).focus();
}
async function closeReview() {
  await api.closeReview();
  $('review-dialog').close();
  review = null;
  $('pictures').replaceChildren();
  $('mermaid-code').value = '';
  for (const viewer of viewers) viewer.clear();
}
async function openComparison() {
  rememberViews();
  await api.fullscreen(true);
  fullscreen = true;
  $('viewer-dialog').showModal();
  updateReviewControls();
  await showViews(true);
  originalExpanded.viewport.focus();
}
async function closeComparison() {
  rememberViews(true);
  if (fullscreen) {
    await api.fullscreen(false);
    fullscreen = false;
  }
  $('viewer-dialog').close();
  await showViews();
}
button('review', async () => {
  review = null;
  $('pictures').replaceChildren();
  $('mermaid-code').value = '';
  originalViewer.clear();
  previewViewer.clear();
  $('review-dialog').showModal();
  updateReviewControls();
  let pictures;
  try {
    pictures = await api.review(selected);
    if (!pictures.length) throw new Error('El documento no contiene imágenes exportadas.');
  } catch (error) {
    await closeReview();
    throw error;
  }
  review = new ReviewSession(selected, pictures);
  drawPictures();
  $('mermaid-code').value = review.current.code;
  await showViews();
}, 'Cargando imágenes y diagramas...');
button('close-review', closeReview);
button('close-viewer', closeComparison, 'Cerrando comparación ampliada...');
for (const [id, close] of [['review-dialog', closeReview], ['viewer-dialog', closeComparison]]) {
  $(id).addEventListener('cancel', event => {
    event.preventDefault();
    if (!uiBusy) void perform(close);
  });
}
$('pictures').addEventListener('keydown', event => {
  if (uiBusy || !review || !['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const current = review.pictures.findIndex(picture => picture.index === review.selected);
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? review.pictures.length - 1
    : Math.max(0, Math.min(review.pictures.length - 1, current + (event.key === 'ArrowDown' ? 1 : -1)));
  const index = review.pictures[next].index;
  void navigatePicture(index);
});
$('mermaid-code').addEventListener('input', () => {
  if (!review || uiBusy) return;
  review.edit($('mermaid-code').value);
  previewViewer.clear();
  updateReviewControls();
});
button('propose', async () => {
  const picture = review.picture;
  const proposal = await api.propose(review.documentId, picture.index, picture.revision);
  if (!proposal) return;
  review.propose(proposal);
  $('mermaid-code').value = review.current.code;
  previewViewer.clear();
}, 'Analizando imagen con IA...');
button('validate', async () => {
  rememberViews();
  review.invalidate();
  previewViewer.clear();
  const picture = review.picture;
  const code = review.current.code;
  const result = await api.validate(review.documentId, picture.index, picture.revision, code, review.current.model);
  review.validate(code, result);
  await showViews();
}, 'Preparando recursos, validando y renderizando Mermaid...');
button('accept', async () => {
  if (!review.canAccept()) throw new Error('Valida de nuevo el código Mermaid.');
  const references = await api.accept(review.current.token);
  if (references) {
    review.accept(references);
    log('Diagrama guardado; imagen original conservada.');
  }
}, 'Guardando el diagrama y actualizando el informe...');

try {
  const initial = await api.state();
  settings = initial.settings;
  rows = initial.rows;
  showDestination();
  drawRows(initial.running);
  log('Añade documentos y selecciona una carpeta de destino.');
} catch (error) { log(error.message); window.alert(error.message); }
