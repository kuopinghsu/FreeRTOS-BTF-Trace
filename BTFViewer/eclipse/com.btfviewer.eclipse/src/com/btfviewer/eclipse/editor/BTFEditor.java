package com.btfviewer.eclipse.editor;

import java.io.IOException;
import java.net.URI;
import java.nio.file.Path;
import java.nio.file.Paths;

import org.eclipse.core.resources.IFile;
import org.eclipse.jface.util.IPropertyChangeListener;
import org.eclipse.swt.SWT;
import org.eclipse.swt.SWTError;
import org.eclipse.swt.browser.Browser;
import org.eclipse.swt.layout.FillLayout;
import org.eclipse.swt.widgets.Composite;
import org.eclipse.swt.widgets.Label;
import org.eclipse.ui.IEditorInput;
import org.eclipse.ui.IEditorSite;
import org.eclipse.ui.IFileEditorInput;
import org.eclipse.ui.IURIEditorInput;
import org.eclipse.ui.PartInitException;
import org.eclipse.ui.PlatformUI;
import org.eclipse.ui.part.EditorPart;

import com.btfviewer.eclipse.BTFViewerPlugin;
import com.btfviewer.eclipse.bridge.BTFBrowserBridge;
import com.btfviewer.eclipse.bridge.BTFBrowserMessage;
import com.btfviewer.eclipse.resources.ViewerResourceServer;
import com.btfviewer.eclipse.util.JsonUtil;

/** Read-only Eclipse shell around the existing BTFViewer HTML application. */
public final class BTFEditor extends EditorPart {
    public static final String EDITOR_ID = "com.btfviewer.eclipse.editor";

    private IFile traceFile;
    private Path localTrace;
    private String traceName;
    private String traceDescription;
    private Browser browser;
    private BTFBrowserBridge bridge;
    private ViewerResourceServer resources;
    private boolean viewerReady;
    private IPropertyChangeListener themeListener;

    @Override
    public void init(IEditorSite site, IEditorInput input) throws PartInitException {
        if (input instanceof IFileEditorInput fileInput) {
            traceFile = fileInput.getFile();
            traceName = traceFile.getName();
            traceDescription = traceFile.getFullPath().toString();
        } else if (input instanceof IURIEditorInput uriInput) {
            URI uri = uriInput.getURI();
            if (uri == null || !"file".equalsIgnoreCase(uri.getScheme())) {
                throw new PartInitException("BTFViewer requires a workspace or local .btf file");
            }
            try {
                localTrace = Paths.get(uri);
            } catch (RuntimeException error) {
                throw new PartInitException("BTFViewer could not resolve the local .btf file", error);
            }
            Path fileName = localTrace.getFileName();
            traceName = fileName == null ? localTrace.toString() : fileName.toString();
            traceDescription = localTrace.toString();
        } else {
            throw new PartInitException("BTFViewer requires a workspace or local .btf file");
        }
        setSite(site);
        setInput(input);
        setPartName("BTF: " + traceName);
    }

    @Override
    public void createPartControl(Composite parent) {
        parent.setLayout(new FillLayout());
        try {
            resources = traceFile != null
                    ? new ViewerResourceServer(BTFViewerPlugin.getDefault().getBundle(), traceFile)
                    : new ViewerResourceServer(BTFViewerPlugin.getDefault().getBundle(), localTrace);
            browser = new Browser(parent, SWT.NONE);
            bridge = new BTFBrowserBridge(browser, this::onBrowserMessage);
            setStatus("Loading viewer...");
            if (!browser.setUrl(resources.viewerUri().toASCIIString())) {
                throw new IOException("SWT Browser rejected the local viewer URL");
            }
            themeListener = event -> applyTheme();
            PlatformUI.getWorkbench().getThemeManager().addPropertyChangeListener(themeListener);
        } catch (IOException | SWTError error) {
            BTFViewerPlugin.log("Unable to initialize the BTFViewer editor", error);
            if (bridge != null && !bridge.isDisposed()) bridge.dispose();
            if (browser != null && !browser.isDisposed()) browser.dispose();
            if (resources != null) resources.close();
            bridge = null;
            browser = null;
            resources = null;
            Label message = new Label(parent, SWT.WRAP);
            message.setText("BTFViewer could not initialize the SWT Browser. See the Eclipse Error Log.");
            setStatus("Error");
        }
    }

    private void onBrowserMessage(BTFBrowserMessage message) {
        if (browser == null || browser.isDisposed()) return;
        switch (message.type()) {
            case "viewerReady" -> {
                viewerReady = true;
                applyTheme();
                call("openTraceUrl", resources.traceUri().toASCIIString(), traceName);
                setStatus("Loading trace...");
            }
            case "traceLoaded" -> setStatus("Ready");
            case "traceLoadFailed" -> {
                setStatus(statusMessage("Error", message.stringValue("message")));
                BTFViewerPlugin.log("BTF trace load failed: " + traceDescription, null);
            }
            case "statusChanged" -> setStatus(statusMessage(
                    message.stringValue("status"), message.stringValue("message")));
            default -> { /* POC receives and validates future messages but has no native action. */ }
        }
    }

    private void applyTheme() {
        if (!viewerReady || browser == null || browser.isDisposed()) return;
        String id = PlatformUI.getWorkbench().getThemeManager().getCurrentTheme().getId();
        call("setTheme", id != null && id.toLowerCase().contains("dark") ? "dark" : "light");
    }

    private void call(String operation, String... arguments) {
        StringBuilder script = new StringBuilder("window.BTFViewerHost.").append(operation).append('(');
        for (int i = 0; i < arguments.length; i++) {
            if (i > 0) script.append(',');
            script.append(JsonUtil.quote(arguments[i]));
        }
        script.append(").catch(function(error){window.BTFViewerHost.notify('statusChanged',"
                + "{status:'Error',message:String(error&&error.message||error)});});");
        if (!browser.execute(script.toString())) {
            BTFViewerPlugin.log("JavaScript operation was rejected: " + operation, null);
        }
    }

    private void setStatus(String message) {
        getEditorSite().getActionBars().getStatusLineManager().setMessage(message);
    }

    private static String statusMessage(String status, String detail) {
        String label = status == null || status.isBlank() ? "BTFViewer" : status;
        return detail == null || detail.isBlank() ? label : label + ": " + detail;
    }

    @Override
    public void setFocus() {
        if (browser != null && !browser.isDisposed()) browser.setFocus();
    }

    @Override public boolean isDirty() { return false; }
    @Override public boolean isSaveAsAllowed() { return false; }
    @Override public void doSave(org.eclipse.core.runtime.IProgressMonitor monitor) {}
    @Override public void doSaveAs() {}

    @Override
    public void dispose() {
        if (themeListener != null) {
            PlatformUI.getWorkbench().getThemeManager().removePropertyChangeListener(themeListener);
            themeListener = null;
        }
        if (bridge != null && !bridge.isDisposed()) bridge.dispose();
        if (resources != null) resources.close();
        bridge = null;
        resources = null;
        browser = null;
        super.dispose();
    }
}
