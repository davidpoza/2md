import mermaid from '../../node_modules/mermaid/dist/mermaid.esm.min.mjs';

mermaid.initialize({
  startOnLoad: false, securityLevel: 'strict', suppressErrorRendering: true, maxTextSize: 100000,
  flowchart: { htmlLabels: false }, htmlLabels: false,
});
window.renderDiagram = async code => {
  await mermaid.parse(code);
  const { svg } = await mermaid.render('local-diagram', code, document.getElementById('diagram'));
  if (/<foreignObject\b|<script\b|\son\w+\s*=|(?:href|src)\s*=\s*["']\s*(?:https?:|\/\/|javascript:)/i.test(svg))
    throw new Error('Mermaid produjo elementos no compatibles con la vista segura.');
  return svg;
};
