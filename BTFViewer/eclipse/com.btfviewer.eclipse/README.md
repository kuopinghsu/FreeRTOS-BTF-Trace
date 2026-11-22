# BTFViewer Eclipse POC

This PDE project is the Phase-0 feasibility implementation. It wraps the same
single-file BTFViewer web application in an SWT `Browser`; it does not port the
timeline, statistics, comparison, reports, or analysis logic to Java.

## Run from Eclipse

1. Run `make -C BTFViewer/web build` and `make -C BTFViewer/eclipse sync-viewer`.
2. Import `BTFViewer/eclipse/com.btfviewer.eclipse` as an existing project.
3. Start an Eclipse Application from the PDE launch configuration.
4. Double-click a workspace `.btf`, `.btf.zip`, `.btf.bz2`, or `.btf.gz`
   file, or use **File > Open File...** for a trace outside the workspace.

## Package for installation

From the repository root, run `make -C BTFViewer eclipse-update-site` to build
the offline installer ZIP in `BTFViewer/builds`. Set `ECLIPSE_HOME` to the
Eclipse directory that contains `plugins` and the p2 publisher. On Windows,
for example:

```powershell
$env:JAVA_HOME = 'C:/path/to/jdk'
make -C BTFViewer eclipse-update-site "ECLIPSE_HOME=C:/path/to/eclipse"
```

See the [Eclipse plug-in guide](../../ECLIPSE_PLUGIN.md) for installation and
the Java requirements for building the update site.

On macOS, the build defaults to `/Applications/Eclipse.app/Contents/Eclipse`.

The editor serves the bundled HTML and selected trace from a tokenized,
loopback-only HTTP endpoint. Trace bytes stream from the workspace or local file
to the browser and are not embedded in a Java string.
