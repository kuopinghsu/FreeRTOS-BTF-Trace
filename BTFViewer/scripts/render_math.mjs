#!/usr/bin/env node
// Renders a JSON array of LaTeX display-math strings (read from stdin) to
// self-contained SVG, using MathJax's SVG output with a *global* glyph
// cache: each formula becomes a small <mjx-container> that <use>-references
// glyph paths in one shared <defs> block, instead of embedding full font
// files (the KaTeX HTML/CSS route) or repeating path data per formula
// (MathJax's own 'local' cache mode). Writes {defs, style, formulas} JSON
// to stdout. Invoked from scripts/build_docs_html.py — see that file for
// why STATISTICS.md's ```math fences need this at all.
import { mathjax } from 'mathjax-full/js/mathjax.js';
import { TeX } from 'mathjax-full/js/input/tex.js';
import { SVG } from 'mathjax-full/js/output/svg.js';
import { liteAdaptor } from 'mathjax-full/js/adaptors/liteAdaptor.js';
import { RegisterHTMLHandler } from 'mathjax-full/js/handlers/html.js';
import { AllPackages } from 'mathjax-full/js/input/tex/AllPackages.js';

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const tex = new TeX({ packages: AllPackages });
const svgJax = new SVG({ fontCache: 'global' });
const doc = mathjax.document('', { InputJax: tex, OutputJax: svgJax });

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => {
  const formulas = JSON.parse(input);
  const rendered = formulas.map((src) => {
    const node = doc.convert(src, { display: true });
    return adaptor.outerHTML(node);
  });
  const defs = adaptor.outerHTML(svgJax.fontCache.defs);
  const style = adaptor.outerHTML(doc.outputJax.styleSheet(doc));
  process.stdout.write(JSON.stringify({ defs, style, formulas: rendered }));
});
