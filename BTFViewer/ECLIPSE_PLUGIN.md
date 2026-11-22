# Eclipse plug-in

Bundle version `0.1.0`.

The optional Eclipse integration embeds the existing BTFViewer HTML/JavaScript
application in an SWT `Browser`. Eclipse supplies workspace and local-file access,
editor lifecycle, initial/live theme synchronization, status reporting, and a
small validated bridge. All trace parsing, Timeline, Statistics, Trace Compare,
Investigation, and report behavior stays in the shared viewer.

## Requirements

- An Eclipse installation with SWT and a Java runtime supported by that Eclipse
  version. The plug-in targets Java 17 bytecode. Eclipse 4.34 is the build
  compatibility baseline.
- On Windows, the editor selects Edge explicitly and requires the Microsoft Edge
  WebView2 Runtime. On Linux GTK and macOS, it uses Eclipse's default SWT
  browser backend. Linux GTK installations typically require WebKitGTK.
  [SWT browser requirements](https://eclipse.dev/eclipse/swt/faq.html)

## Install

Extract `com.btfviewer.eclipse_0.1.0-p2.zip` from the
[BTFViewer release package](https://github.com/kuopinghsu/FreeRTOS-BTF-Trace/releases),
download the standalone installer asset, or use the
[installer ZIP in the repository](builds/com.btfviewer.eclipse_0.1.0-p2.zip).
Keep the p2 ZIP intact.

1. If you previously installed BTFViewer in `dropins/`, close Eclipse,
   remove that copy, and restart Eclipse before installing with the wizard.
2. In Eclipse, open **Help > Install New Software… > Add… > Archive…**.
   Select the downloaded ZIP and choose **Add**.
3. Expand the **BTFViewer** category, select **BTFViewer**, and complete
   the wizard. Restart Eclipse when prompted.

To remove the plug-in, select **BTFViewer** under **Help > About Eclipse IDE >
Installation Details > Installed Software**, then choose **Uninstall…**.
For Eclipse distributions without the installation wizard, build the bundle JAR
with `make -C BTFViewer eclipse-package` and copy it to `dropins/` with Eclipse
closed. Restart Eclipse with `-clean` after changing that folder.

## Open a trace

Double-click a workspace `.btf`, `.btf.zip`, `.btf.bz2`, or `.btf.gz` file,
or use **File > Open File…** for a local trace outside the workspace. If another
editor opens the file, use **Open With > BTFViewer Editor**. Each trace opens in
a read-only tab titled `BTF: <filename>`.

If the editor cannot initialize its browser or fails to start within 30
seconds, check the Eclipse Error Log. On Windows, verify that WebView2 is
installed if the editor reports a browser initialization error.

## Build from source

Packaging rebuilds the shared HTML and compiles the OSGi JAR into
`BTFViewer/builds`. The build needs GNU Make, Node.js 22 or newer with npm,
and a JDK 17 or newer with `javac` and `jar`. On Windows, the Makefiles use
Git for Windows' shell. Set `GIT_SH` if Git is installed in a different location.

Run the command from the repository root. Set `ECLIPSE_HOME` to the directory
that contains `plugins/`. On macOS, the default is
`/Applications/Eclipse.app/Contents/Eclipse`.

```sh
make -C BTFViewer eclipse-package ECLIPSE_HOME=/path/to/eclipse
```

```powershell
$env:JAVA_HOME = 'C:/path/to/jdk'
make -C BTFViewer eclipse-package "ECLIPSE_HOME=C:/Program Files/eclipse"
```

The build looks for the JDK in `JAVA_HOME`, on `PATH`, and in common Windows
install locations. If the Eclipse plug-ins are in a separate directory, set
`ECLIPSE_PLUGINS` to that directory directly.

### Build the offline installer

Use Python 3.9 or later and an Eclipse SDK with the p2 publisher installed.
Use a Java runtime supported by that SDK. The publisher uses `JAVA_HOME`
when set. Otherwise, it looks for Eclipse's bundled Java, a JDK discovered
on Windows, or Java on `PATH`.

Run the normal build with `ECLIPSE_HOME` set to the SDK directory. When the p2
publisher is present, the build writes the installer ZIP and cleans up the
temporary JAR after packaging it inside the ZIP. When the publisher is absent,
the build skips Eclipse packaging. Use `eclipse-package` explicitly if you need
a standalone JAR for manual installation.

```powershell
$env:ECLIPSE_HOME = 'C:/Program Files/eclipse'
make -C BTFViewer
```

To build just the Eclipse installer and its web viewer, run
`eclipse-update-site` explicitly. This target requires the publisher.

```sh
make -C BTFViewer eclipse-update-site "ECLIPSE_HOME=/path/to/eclipse"
```

Both builds write `com.btfviewer.eclipse_0.1.0-p2.zip` to `BTFViewer/builds`.
Bump the Eclipse bundle version and rebuild the JAR before distributing
changed plug-in contents through p2. Eclipse uses the feature and bundle
versions to identify updates.

For PDE development, run `make -C BTFViewer eclipse-poc` to build and sync
the embedded viewer, then follow the
[plug-in project instructions](eclipse/com.btfviewer.eclipse/README.md).

## Verify the bundle

```sh
make -C BTFViewer check-eclipse-resources
make -C BTFViewer check-eclipse ECLIPSE_HOME=/path/to/eclipse
```

The CI resource check compares the packaged HTML, editor declaration, icons,
bundle version, and Java class presence with the repository. The local check
also recompiles against the configured Eclipse installation and compares the
class list. It compares bytecode when the compiler version matches the one
recorded in the JAR.

Rebuild and commit the installer ZIP when changing the plug-in sources, metadata,
icons, or shared web viewer. To verify behavior in an Eclipse installation,
open a plain trace and a compressed trace, check the timeline and Statistics,
switch between light and dark themes, and test any export formats you use.

## Browser and data path

Each editor owns a tokenized HTTP server bound to `127.0.0.1`. It streams
the selected trace as bytes to the shared loader. The server caps transferred
trace bytes at 256 MiB, and the viewer caps decompressed trace data at 256 MiB.
Closing the editor closes the server and its active connections. The packaged
HTML matches the standalone [web build](builds/btf_viewer.html) byte for byte.

## Theme and bridge

Eclipse light/dark theme changes call the viewer's existing dark-mode setting
without reloading the trace. The bridge accepts an allowlist of message types.
The editor acts on `viewerReady`, `traceLoaded`, `traceLoadFailed`, and
`statusChanged`.

## Known limitations

- AI network access and export downloads depend on the SWT browser backend.
- The integration provides manual JAR installation and exposes comparison,
  settings, and reports through the embedded viewer.
