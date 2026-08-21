# BTFViewer beginner presentation

This Quarto Reveal.js deck introduces BTFViewer to a first-time user. It
explains the interface, the information available in a trace, an eight-step
investigation workflow, Statistics, cursor-scoped verification, and the safe
use of AI assistance. The theme uses presentation-sized text and prominent
numbered step badges for readability on a projected screen.

## Preview

```bash
quarto preview slides.qmd
```

Extract this package into a new, empty directory and run the command from that
directory. The ZIP is intentionally flat: `slides.qmd` and `_quarto.yml` are at
its root, so an older project file cannot be selected accidentally.

## Render the HTML presentation

```bash
quarto render slides.qmd
```

The generated presentation is written to `_site/slides.html`. The project uses
Quarto Reveal.js, Mermaid, speaker notes, a custom SCSS theme, a cover PNG, and
the supplied core-migration heatmap in SVG and PNG formats.

The source deck contains 35 horizontal slides. Keep headings at level two
(`##`) so Reveal.js navigation stays linear.

To confirm the generated slide count:

```bash
grep -o 'class="slide level2' _site/slides.html | wc -l
```

The expected result is `35`. If the browser still shows an older count, close
the old tab, render again, and reopen `_site/slides.html` with a hard refresh.
