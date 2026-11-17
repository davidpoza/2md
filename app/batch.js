import path from 'node:path';
import { convertDocument } from './conversion.js';
import { readJson, sha256 } from './files.js';
import { atomicWrite } from './config.js';
import { pictureReferences, storeDiagram } from './review.js';
import { proposeDiagram } from './ai.js';

function semaphore(limit) {
  let active = 0;
  const waiting = [];
  return async operation => {
    if (active >= limit) await new Promise(resolve => waiting.push(resolve));
    else active++;
    try { return await operation(); }
    finally {
      const next = waiting.shift();
      if (next) next();
      else active--;
    }
  };
}
export async function automaticDiagrams(outcome, settings, signal, render, requestSlot, activity) {
  const reportFile = path.join(path.dirname(outcome.markdown), 'conversion-report.json');
  const report = await readJson(reportFile);
  const processed = new Set(report.imagenes_analizadas_ia || []);
  const warnings = outcome.warnings.filter(item => !item.startsWith('Análisis automático de imagen '));
  let retryable = false;
  try {
    const count = (await pictureReferences(outcome.markdown)).length;
    for (let index = 1; index <= count; index++) {
      signal.throwIfAborted();
      if (processed.has(index)) continue;
      const reference = (await pictureReferences(outcome.markdown))[index - 1];
      if (reference.stored) { processed.add(index); continue; }
      activity(`Imagen ${index}/${count}: esperando disponibilidad para IA.`);
      try {
        const proposal = await requestSlot(async () => {
          signal.throwIfAborted();
          return proposeDiagram(reference, settings, signal, activity);
        });
        signal.throwIfAborted();
        if (proposal.fiable && proposal.mermaid) {
          await render(proposal.mermaid);
          signal.throwIfAborted();
          await storeDiagram(outcome.markdown, reference, proposal.mermaid, settings.ai.model, true);
          activity(`Imagen ${index}/${count}: diagrama pendiente de revisión.`);
        } else activity(`Imagen ${index}/${count}: sin propuesta fiable.`);
        processed.add(index);
      } catch (error) {
        if (signal.aborted) throw error;
        const warning = `Análisis automático de imagen ${index}: ${error.message}`;
        warnings.push(warning);
        activity(warning);
        retryable = true;
      }
    }
  } finally {
    const current = await readJson(reportFile);
    Object.assign(current, {
      imagenes_analizadas_ia: [...processed].sort((a, b) => a - b),
      advertencias: warnings, errores_ia: retryable,
      estado: warnings.length ? 'completado_con_advertencias' : 'completado',
    });
    await atomicWrite(reportFile, `${JSON.stringify(current, null, 2)}\n`);
  }
  return { ...outcome, warnings, retryable };
}

export class Batch {
  constructor(notify, render) {
    this.notify = notify;
    this.render = render;
    this.rows = [];
    this.running = false;
  }
  add(files) {
    for (const source of files) {
      if (!this.rows.some(row => row.source.toLowerCase() === source.toLowerCase()))
        this.rows.push({ id: this.rows.length, source, state: 'Pendiente', progress: 0, outcome: null });
    }
    this.emit();
  }
  emit() { this.notify({ type: 'rows', rows: this.rows, running: this.running }); }
  cancel() { this.controller?.abort(new Error('Conversión cancelada.')); }
  async run(settings, automatic, retry = false) {
    if (this.running) throw new Error('Ya hay un lote en curso.');
    const pending = this.rows.filter(row => retry
      ? ['Error', 'Cancelado'].includes(row.state) || row.outcome?.retryable
      : row.state === 'Pendiente');
    if (!pending.length) throw new Error('No hay documentos pendientes o reintentables.');
    if (!settings.output_directory) throw new Error('Selecciona una carpeta de destino.');
    this.running = true;
    this.controller = new AbortController();
    const signal = this.controller.signal;
    const slot = semaphore(settings.ai.concurrency);
    const variant = automatic ? sha256(JSON.stringify({ ai: settings.ai, renderer: 'mermaid-11.12.2' })) : '';
    let done = 0;
    const total = pending.length;
    this.notify({ type: 'progress', done: 0, total });
    this.emit();
    const worker = async () => {
      while (pending.length) {
        const row = pending.shift();
        if (signal.aborted) {
          row.state = 'Cancelado';
          done++;
          this.notify({ type: 'progress', done, total });
          this.emit();
          continue;
        }
        row.state = 'Convirtiendo';
        row.progress = 0;
        this.emit();
        const activity = message => this.notify({ type: 'activity', message: `${path.basename(row.source)}: ${message}` });
        try {
          row.outcome = await convertDocument(row.source, settings.output_directory, { signal, variant });
          row.progress = automatic ? 80 : 100;
          if (automatic) {
            row.state = 'Analizando imágenes';
            this.emit();
            row.outcome = await automaticDiagrams(row.outcome, settings, signal, this.render, slot, activity);
          }
          row.state = row.outcome.warnings.length ? 'Completado con advertencias' : 'Completado';
          row.progress = 100;
          for (const warning of row.outcome.warnings) activity(warning);
        } catch (error) {
          row.state = signal.aborted ? 'Cancelado' : 'Error';
          activity(error.message);
        }
        done++;
        this.notify({ type: 'progress', done, total });
        this.emit();
      }
    };
    try { await Promise.all(Array.from({ length: Math.min(settings.document_concurrency, pending.length) }, worker)); }
    finally { this.running = false; this.emit(); }
  }
}
