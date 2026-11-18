import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ReviewSession } from '../app/renderer/review-state.js';

function session() {
  return new ReviewSession(7, [
    { index: 1, revision: 'original', name: 'one.png', stored: null },
    { index: 2, revision: 'original', name: 'two.png', stored: null },
  ]);
}
test('navigation preserves each diagram draft, validation, preview, message and viewport', () => {
  const review = session();
  review.propose({ fiable: true, mermaid: 'flowchart LR\nA --> B', categoria: 'flujo', motivo: 'Propuesta', model: 'vision-model' });
  review.validate(review.current.code, { token: 'first', svg: '<svg>first</svg>' });
  review.current.originalView = { scale: 2, fitted: false, center: { x: 30, y: 40 } };
  review.current.previewView = { scale: 3, fitted: false, center: { x: 50, y: 60 } };
  const first = structuredClone(review.current);
  review.select(2);
  review.edit('sequenceDiagram\nAlice->>Bob: Hello');
  review.validate(review.current.code, { token: 'second', svg: '<svg>second</svg>' });
  review.select(1);
  assert.deepEqual(review.current, first);
  assert.equal(review.canAccept(), true);
  review.edit('flowchart LR\nA --> C');
  assert.equal(review.canAccept(), false);
  assert.equal(review.current.svg, null);
  review.select(2);
  assert.equal(review.canAccept(), true);
  assert.equal(review.current.token, 'second');
  assert.equal(review.current.svg, '<svg>second</svg>');
});
test('saving one diagram preserves other validated drafts and refreshes all revisions', () => {
  const review = session();
  review.edit('flowchart LR\nA --> B');
  review.validate(review.current.code, { token: 'first', svg: '<svg>first</svg>' });
  review.select(2);
  review.edit('flowchart LR\nC --> D');
  review.validate(review.current.code, { token: 'second', svg: '<svg>second</svg>' });
  const second = structuredClone(review.current);
  review.select(1);
  review.accept([
    { index: 1, revision: 'after-save', stored: { code: review.current.code, pending: false } },
    { index: 2, revision: 'after-save', stored: null },
  ]);
  assert.equal(review.selected, 1);
  assert.equal(review.status(1), 'Aceptado');
  assert.equal(review.canAccept(), false);
  review.select(2);
  assert.deepEqual(review.current, second);
  assert.equal(review.picture.revision, 'after-save');
  assert.equal(review.canAccept(), true);
  assert.equal(review.picture.name, 'two.png');
});
test('updating an accepted diagram requires a new validation and keeps the accepted marker until edited', () => {
  const review = new ReviewSession(7, [{
    index: 1, revision: 'original', stored: { code: 'flowchart LR\nA --> B', pending: false },
  }]);
  assert.equal(review.status(1), 'Aceptado');
  review.edit('flowchart LR\nA --> C');
  assert.equal(review.status(1), 'Modificado; pendiente de validación');
  assert.equal(review.canAccept(), false);
  review.validate(review.current.code, { token: 'replacement', svg: '<svg>replacement</svg>' });
  assert.equal(review.canAccept(), true);
  assert.equal(review.status(1), 'Validado; pendiente de aceptación');
});
