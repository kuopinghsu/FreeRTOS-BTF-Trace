# BTFViewer Eclipse POC

This PDE project is the Phase-0 feasibility implementation. It wraps the same
single-file BTFViewer web application in an SWT `Browser`; it does not port the
timeline, statistics, comparison, reports, or analysis logic to Java.

## Run from Eclipse

1. Run `make -C BTFViewer/web build` and `make -C BTFViewer/eclipse sync-viewer`.
2. Import `BTFViewer/eclipse/com.btfviewer.eclipse` as an existing project.
3. Start an Eclipse Application from the PDE launch configuration.
4. Double-click a workspace `.btf` file, or use **File > Open File...** for a
   local `.btf` file outside the workspace.

## Package for installation

From the repository root, run `make -C BTFViewer eclipse-package`. The build
places the installable plug-in JAR in `BTFViewer/builds`. Copy that JAR into
Eclipse's `dropins/` directory after removing any older copy, then restart once
with `-clean`. Set `ECLIPSE_HOME=/path/to/eclipse` when Eclipse is not installed
at the default macOS location.

The editor serves the bundled HTML and selected trace from a tokenized,
loopback-only HTTP endpoint. Trace bytes stream from the workspace or local file
to the browser and are not embedded in a Java string.

Only `.btf` is associated in this POC. Registering generic `.gz`, `.bz2`, or
`.zip` extensions would incorrectly claim unrelated workspace files.
