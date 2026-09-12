# Eclipse plug-in

Status: Phase-0 feasibility POC (`0.1.0`).

The optional Eclipse integration embeds the existing BTFViewer HTML/JavaScript
application in an SWT `Browser`. Eclipse supplies workspace-file access,
editor lifecycle, initial/live theme synchronization, status reporting, and a
small validated bridge. All trace parsing, Timeline, Statistics, Trace Compare,
Investigation, and report behavior stays in the shared viewer.

## Requirements

- Eclipse IDE with PDE and Java 17 or later
- An SWT Browser backend with modern JavaScript enabled
- A workspace `.btf` file

## Build and install for POC testing

```sh
make -C BTFViewer/web build
make -C BTFViewer/eclipse sync-viewer check-viewer
```

Import `BTFViewer/eclipse/com.btfviewer.eclipse` into an Eclipse PDE workspace
and launch an Eclipse Application. The POC is intentionally not yet shipped as
a feature or p2 repository; the implementation checklist explicitly gates that
work on cross-platform browser validation.

## Open a trace

Import a `.btf` file into a project and double-click it. The read-only editor is
named `BTF: <filename>`. Multiple workspace files can be opened in separate
editor tabs. Reload, native commands, preferences, and external-file editor
inputs belong to later milestones after the feasibility gate.

## Browser and data path

Each editor owns a tokenized HTTP server bound only to `127.0.0.1`. It streams
the selected `IFile` directly to the shared JavaScript loader, avoiding a full
`Java String -> JSON -> browser.execute` trace copy. Closing the editor closes
the server. The bundled viewer is generated from the normal web build and must
remain byte-for-byte identical to `BTFViewer/builds/btf_viewer.html`.

## Theme and bridge

Eclipse light/dark theme changes call the viewer's existing dark-mode setting
without reloading the trace. JavaScript messages are limited to an allowlist;
the browser cannot choose arbitrary Java method names. The POC implements
`viewerReady`, `traceLoaded`, `traceLoadFailed`, and status handling.

## Required feasibility validation

Before later milestones begin, manually verify the same POC on Windows, Linux
GTK, and macOS. Record Eclipse/SWT versions and results for CSS Grid, Flexbox,
SVG, Canvas, Timeline rendering, large tables, dark mode, Trace Compare,
reports, localStorage, Blob, URL.createObjectURL, Promise, async/await, fetch,
and matchMedia. This repository environment can build and unit-test the shared
viewer but cannot certify the unavailable operating systems or SWT backends.

## Known limitations

- Only workspace `.btf` inputs are registered.
- AI network access depends on the SWT browser's networking/CORS behavior and
  is not part of the initial gate.
- Export downloads and platform-specific SWT Browser behavior require manual
  validation.
- Packaging, commands, preferences, secure storage, reload, and native compare
  selection are deliberately deferred by the Phase-0 gate.

