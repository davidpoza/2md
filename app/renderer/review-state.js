export class ReviewSession {
  constructor(documentId, pictures) {
    this.documentId = documentId;
    this.pictures = pictures;
    this.selected = pictures[0]?.index ?? null;
    this.states = new Map(pictures.map(picture => [picture.index, {
      code: picture.stored?.code || '',
      acceptedCode: picture.stored && !picture.stored.pending ? picture.stored.code.trim() : null,
      validatedCode: null,
      token: null,
      svg: null,
      model: null,
      message: picture.stored
        ? picture.stored.pending ? 'Propuesta automática pendiente de revisión. Valídala y compárala con la imagen.'
          : 'Diagrama aceptado. Valídalo para cargar la previsualización.'
        : 'Genera una propuesta o introduce Mermaid manualmente.',
      originalView: null,
      previewView: null,
    }]));
  }
  get picture() { return this.pictures.find(picture => picture.index === this.selected); }
  get current() { return this.states.get(this.selected); }
  select(index) {
    if (!this.states.has(index)) throw new Error('Diagrama desconocido.');
    this.selected = index;
  }
  invalidate() {
    Object.assign(this.current, { validatedCode: null, token: null, svg: null, previewView: null });
  }
  edit(code) {
    this.current.code = code;
    this.invalidate();
    this.current.message = this.current.acceptedCode !== null
      ? 'Diagrama modificado. Vuelve a validarlo y aceptarlo.'
      : 'Código pendiente de validación.';
  }
  propose(proposal) {
    this.edit(proposal.fiable ? proposal.mermaid : '');
    this.current.model = proposal.model;
    this.current.message = `${proposal.categoria}: ${proposal.motivo || (proposal.fiable ? 'Propuesta pendiente de validación y revisión.' : 'Sin propuesta fiable.')}`;
  }
  validate(code, result) {
    if (this.current.code !== code) throw new Error('El código cambió durante la validación.');
    Object.assign(this.current, {
      validatedCode: code, token: result.token, svg: result.svg, previewView: null,
      message: 'Validación correcta. Compara visualmente el resultado antes de aceptar.',
    });
  }
  accept(references) {
    if (!this.canAccept()) throw new Error('Valida de nuevo el código Mermaid.');
    for (const reference of references) {
      const picture = this.pictures.find(item => item.index === reference.index);
      if (!picture) throw new Error('La lista de imágenes cambió; vuelve a abrir la revisión.');
      Object.assign(picture, reference);
    }
    this.current.acceptedCode = this.current.code.trim();
    this.current.message = 'Diagrama guardado. Se conserva la imagen original.';
  }
  canAccept() {
    const state = this.current;
    return Boolean(state?.token && state.svg && state.validatedCode === state.code &&
      state.code.trim() !== state.acceptedCode);
  }
  status(index) {
    const state = this.states.get(index);
    const picture = this.pictures.find(item => item.index === index);
    if (state.acceptedCode !== null && state.code.trim() === state.acceptedCode) return 'Aceptado';
    if (state.token && state.validatedCode === state.code) return 'Validado; pendiente de aceptación';
    if (state.acceptedCode !== null) return 'Modificado; pendiente de validación';
    if (picture.stored?.pending && state.code === picture.stored.code) return 'Pendiente de revisión humana';
    return state.code.trim() ? 'Pendiente de validación' : 'Sin diagrama';
  }
}
