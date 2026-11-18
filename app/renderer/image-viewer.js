const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

export class ImageViewer {
  constructor(root, title, expand) {
    root.append(document.getElementById('image-viewer-template').content.cloneNode(true));
    root.querySelector('.viewer-title').textContent = title;
    this.viewport = root.querySelector('.image-viewport');
    this.viewport.setAttribute('aria-label', `${title}. Rueda para zoom, arrastrar para desplazar.`);
    this.canvas = root.querySelector('.image-canvas');
    this.image = root.querySelector('img');
    this.placeholder = root.querySelector('.viewer-placeholder');
    this.zoomLabel = root.querySelector('.viewer-zoom');
    this.buttons = [...root.querySelectorAll('button')];
    this.scale = 1;
    this.fitted = true;
    this.source = null;
    this.ready = false;
    this.disabled = false;
    this.drag = null;
    const actions = {
      out: () => this.zoom(0.8), in: () => this.zoom(1.25),
      actual: () => this.actualSize(), fit: () => this.fit(), expand,
    };
    for (const button of this.buttons) {
      const action = actions[button.dataset.action];
      button.hidden = !action;
      button.addEventListener('click', () => {
        if (!this.disabled && this.ready) {
          action();
          if (button.dataset.action !== 'expand') this.viewport.focus();
        }
      });
    }
    this.viewport.addEventListener('wheel', event => {
      if (this.disabled || !this.ready) return;
      event.preventDefault();
      const bounds = this.viewport.getBoundingClientRect();
      if (event.deltaY) this.zoom(event.deltaY < 0 ? 1.25 : 0.8,
        event.clientX - bounds.left - this.viewport.clientLeft, event.clientY - bounds.top - this.viewport.clientTop);
    }, { passive: false });
    this.viewport.addEventListener('pointerdown', event => {
      if (event.button !== 0 || !this.ready || this.disabled) return;
      const bounds = this.viewport.getBoundingClientRect();
      if (event.clientX - bounds.left - this.viewport.clientLeft >= this.viewport.clientWidth ||
          event.clientY - bounds.top - this.viewport.clientTop >= this.viewport.clientHeight) return;
      this.viewport.focus();
      this.viewport.setPointerCapture(event.pointerId);
      this.drag = { id: event.pointerId, x: event.clientX, y: event.clientY,
        left: this.viewport.scrollLeft, top: this.viewport.scrollTop };
      this.viewport.classList.add('dragging');
      event.preventDefault();
    });
    this.viewport.addEventListener('pointermove', event => {
      if (this.drag?.id !== event.pointerId) return;
      this.viewport.scrollLeft = this.drag.left - event.clientX + this.drag.x;
      this.viewport.scrollTop = this.drag.top - event.clientY + this.drag.y;
    });
    const endDrag = () => { this.drag = null; this.viewport.classList.remove('dragging'); };
    this.viewport.addEventListener('lostpointercapture', endDrag);
    this.viewport.addEventListener('pointerup', event => {
      if (this.viewport.hasPointerCapture(event.pointerId)) this.viewport.releasePointerCapture(event.pointerId);
      endDrag();
    });
    this.viewport.addEventListener('keydown', event => {
      if (!this.ready || this.disabled) return;
      const action = { '+': actions.in, '=': actions.in, '-': actions.out, '0': actions.actual, f: actions.fit, F: actions.fit }[event.key];
      if (action) { event.preventDefault(); action(); }
    });
    this.observer = new ResizeObserver(() => {
      if (!this.ready || !this.viewport.clientWidth || !this.viewport.clientHeight) return;
      if (this.fitted) this.fit();
      else this.layout(this.center);
    });
    this.observer.observe(this.viewport);
    this.viewport.addEventListener('scroll', () => { if (this.ready) this.center = this.imagePoint(); });
    this.updateControls();
  }
  setDisabled(disabled) {
    this.disabled = disabled;
    this.viewport.tabIndex = disabled ? -1 : 0;
    this.viewport.setAttribute('aria-disabled', String(disabled));
    this.updateControls();
  }
  updateControls() {
    for (const button of this.buttons) button.disabled = this.disabled || !this.ready;
    this.zoomLabel.textContent = this.ready ? `${Math.round(this.scale * 100)} %` : '';
  }
  clear(message = 'Sin previsualización') {
    this.source = null;
    this.ready = false;
    this.image.removeAttribute('src');
    this.image.hidden = true;
    this.canvas.hidden = true;
    this.placeholder.hidden = false;
    this.placeholder.textContent = message;
    this.updateControls();
  }
  async show(source, state = null, dimensions = null) {
    if (!source) { this.clear(); return; }
    if (this.source !== source || !this.ready) {
      this.clear('Cargando imagen...');
      this.source = source;
      this.image.src = source;
      try { await this.image.decode(); }
      catch {
        this.clear('No se pudo abrir la imagen en el visor.');
        throw new Error('No se pudo abrir la imagen en el visor.');
      }
      this.width = dimensions?.width || this.image.naturalWidth;
      this.height = dimensions?.height || this.image.naturalHeight;
      if (!this.width || !this.height) {
        this.clear('La imagen no tiene dimensiones válidas.');
        throw new Error('La imagen no tiene dimensiones válidas.');
      }
      this.ready = true;
      this.image.hidden = false;
      this.canvas.hidden = false;
      this.placeholder.hidden = true;
    }
    this.fitted = state?.fitted ?? true;
    if (this.fitted) this.fit();
    else { this.scale = clamp(state.scale, 0.01, 32); this.layout(state.center); }
    this.updateControls();
  }
  imagePoint(x = this.viewport.clientWidth / 2, y = this.viewport.clientHeight / 2) {
    return {
      x: (this.viewport.scrollLeft + x - this.left) / this.scale,
      y: (this.viewport.scrollTop + y - this.top) / this.scale,
    };
  }
  layout(center = { x: this.width / 2, y: this.height / 2 }, anchor) {
    const width = this.width * this.scale;
    const height = this.height * this.scale;
    const viewportWidth = this.viewport.clientWidth;
    const viewportHeight = this.viewport.clientHeight;
    this.left = Math.max(0, (viewportWidth - width) / 2);
    this.top = Math.max(0, (viewportHeight - height) / 2);
    this.canvas.style.width = `${Math.max(viewportWidth, width)}px`;
    this.canvas.style.height = `${Math.max(viewportHeight, height)}px`;
    this.image.style.width = `${width}px`;
    this.image.style.height = `${height}px`;
    this.image.style.left = `${this.left}px`;
    this.image.style.top = `${this.top}px`;
    this.viewport.scrollLeft = this.left + center.x * this.scale - (anchor?.x ?? viewportWidth / 2);
    this.viewport.scrollTop = this.top + center.y * this.scale - (anchor?.y ?? viewportHeight / 2);
    this.center = this.imagePoint();
    this.updateControls();
  }
  fit() {
    if (!this.ready || !this.viewport.clientWidth || !this.viewport.clientHeight) return;
    this.fitted = true;
    this.scale = clamp(Math.min(this.viewport.clientWidth / this.width, this.viewport.clientHeight / this.height), 0.01, 32);
    this.layout();
  }
  actualSize() {
    if (!this.ready) return;
    this.fitted = false;
    this.scale = 1;
    this.layout();
  }
  zoom(factor, x = this.viewport.clientWidth / 2, y = this.viewport.clientHeight / 2) {
    const point = this.imagePoint(x, y);
    this.fitted = false;
    this.scale = clamp(this.scale * factor, 0.01, 32);
    this.layout(point, { x, y });
  }
  snapshot() {
    return this.ready ? { scale: this.scale, fitted: this.fitted, center: this.imagePoint() } : null;
  }
}

export function svgSource(svg) {
  const document = new DOMParser().parseFromString(svg, 'image/svg+xml');
  const viewBox = document.documentElement.getAttribute('viewBox')?.trim().split(/[\s,]+/).map(Number);
  const dimensions = viewBox?.length === 4 && viewBox.every(Number.isFinite) && viewBox[2] > 0 && viewBox[3] > 0
    ? { width: viewBox[2], height: viewBox[3] } : null;
  const bytes = new TextEncoder().encode(svg);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return { source: `data:image/svg+xml;base64,${btoa(binary)}`, dimensions };
}
