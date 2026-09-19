# Eclipse plug-in

Status: Phase-0 feasibility POC (`0.1.0`).

The optional Eclipse integration embeds the existing BTFViewer HTML/JavaScript
application in an SWT `Browser`. Eclipse supplies workspace and local-file access,
editor lifecycle, initial/live theme synchronization, status reporting, and a
small validated bridge. All trace parsing, Timeline, Statistics, Trace Compare,
Investigation, and report behavior stays in the shared viewer.

## Requirements

- Eclipse IDE with PDE and Java 17 or later
- An SWT Browser backend with modern JavaScript enabled
- A workspace or local `.btf` file

## Build and install

```sh
make -C BTFViewer eclipse-package
```

This produces one artifact in `BTFViewer/builds`:

- `com.btfviewer.eclipse_0.1.0.jar` — the compiled OSGi plug-in bundle.

To install, close Eclipse, remove any older `com.btfviewer.eclipse_*.jar` from
Eclipse's `dropins/` directory, and copy the plug-in JAR into that directory.
Restart Eclipse with `-clean` once so its bundle cache is refreshed.

The committed JAR is a generated build artifact, like `builds/btf_viewer.{html,py}`,
and has its own freshness gates:

```sh
make -C BTFViewer check-eclipse-resources # CI-safe: packaged web/plugin.xml/icons/
                                           # manifest version/class list vs. sources
make -C BTFViewer check-eclipse           # + full recompile-and-bytecode-diff
                                           # (needs ECLIPSE_HOME; skips without one)
```

`check-eclipse-resources` runs in CI on every push/PR (no Eclipse SDK needed);
`check-eclipse` is the stronger local gate for a machine with Eclipse installed.
After changing plug-in sources, the embedded web viewer, `plugin.xml`, or icons,
re-run `eclipse-package` and commit the updated JAR.

The build defaults to `/Applications/Eclipse.app/Contents/Eclipse` on macOS.
For another installation, pass its root explicitly:

```sh
make -C BTFViewer eclipse-package ECLIPSE_HOME=/path/to/eclipse
```

For PDE development, import `BTFViewer/eclipse/com.btfviewer.eclipse` into an
Eclipse workspace and launch an Eclipse Application.

## Open a trace

Double-click a workspace `.btf` file, or use **File > Open File...** for a local
file outside the workspace. The read-only editor is named `BTF: <filename>`.
Multiple files can be opened in separate editor tabs. Reload, native commands,
and preferences belong to later milestones after the feasibility gate.

## Browser and data path

Each editor owns a tokenized HTTP server bound only to `127.0.0.1`. It streams
the selected workspace or local file directly to the shared JavaScript loader, avoiding a full
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

- AI network access depends on the SWT browser's networking/CORS behavior and
  is not part of the initial gate.
- Export downloads and platform-specific SWT Browser behavior require manual
  validation.
- A signed p2 update site, commands, preferences, secure storage, reload, and
  native compare selection are deferred beyond the Phase-0 gate.
