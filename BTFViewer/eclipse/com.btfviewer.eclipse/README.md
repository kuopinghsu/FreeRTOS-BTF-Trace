# BTFViewer Eclipse POC

This PDE project is the Phase-0 feasibility implementation. It wraps the same
single-file BTFViewer web application in an SWT `Browser`; it does not port the
timeline, statistics, comparison, reports, or analysis logic to Java.

## Run from Eclipse

1. Run `make -C BTFViewer/web build` and `make -C BTFViewer/eclipse sync-viewer`.
2. Import `BTFViewer/eclipse/com.btfviewer.eclipse` as an existing project.
3. Start an Eclipse Application from the PDE launch configuration.
4. Import a `.btf` file into a workspace project and double-click it.

The editor serves the bundled HTML and selected trace from a tokenized,
loopback-only HTTP endpoint. Trace bytes stream from `IFile.getContents()` to
the browser and are not embedded in a Java string.

Only `.btf` is associated in this POC. Registering generic `.gz`, `.bz2`, or
`.zip` extensions would incorrectly claim unrelated workspace files.

