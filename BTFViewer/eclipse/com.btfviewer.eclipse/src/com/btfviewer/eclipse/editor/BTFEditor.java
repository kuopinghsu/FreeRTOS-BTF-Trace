package com.btfviewer.eclipse.editor;

import java.io.IOException;

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
    private Browser browser;
    private BTFBrowserBridge bridge;
    private ViewerResourceServer resources;
    private boolean viewerReady;
    private IPropertyChangeListener themeListener;

    @Override
    public void init(IEditorSite site, IEditorInput input) throws PartInitException {
        if (!(input instanceof IFileEditorInput fileInput)) {
            throw new PartInitException("BTFViewer 0.1.0 requires an Eclipse workspace file");
        }
        traceFile = fileInput.getFile();
        setSite(site);
        setInput(input);
        setPartName("BTF: " + traceFile.getName());
    }

    @Override
    public void createPartControl(Composite parent) {
        parent.setLayout(new FillLayout());
        try {
            resources = new ViewerResourceServer(BTFViewerPlugin.getDefault().getBundle(), traceFile);
            browser = new Browser(parent, SWT.NONE);
            bridge = new BTFBrowserBridge(browser, this::onBrowserMessage);
            themeListener = event -> applyTheme();
            PlatformUI.getWorkbench().getThemeManager().addPropertyChangeListener(themeListener);
            setStatus("Loading viewer...");
            if (!browser.setUrl(resources.viewerUri().toASCIIString())) {
                throw new IOException("SWT Browser rejected the local viewer URL");
            }
        } catch (IOException | SWTError error) {
            BTFViewerPlugin.log("Unable to initialize the BTFViewer editor", error);
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
                call("openTraceUrl", resources.traceUri().toASCIIString(), traceFile.getName());
                setStatus("Loading trace...");
            }
            case "traceLoaded" -> setStatus("Ready");
            case "traceLoadFailed" -> {
                setStatus("Error");
                BTFViewerPlugin.log("BTF trace load failed: " + traceFile.getFullPath(), null);
            }
            case "statusChanged" -> setStatus("BTFViewer");
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
                + "{status:'Error',message:String(error)});});");
        if (!browser.execute(script.toString())) {
            BTFViewerPlugin.log("JavaScript operation was rejected: " + operation, null);
        }
    }

    private void setStatus(String message) {
        getEditorSite().getActionBars().getStatusLineManager().setMessage(message);
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

