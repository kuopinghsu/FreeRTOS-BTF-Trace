package com.btfviewer.eclipse.editor;

import java.io.IOException;
import java.net.URI;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.LinkedHashSet;
import java.util.Set;

import org.eclipse.core.resources.IFile;
import org.eclipse.jface.util.IPropertyChangeListener;
import org.eclipse.swt.SWT;
import org.eclipse.swt.SWTError;
import org.eclipse.swt.browser.Browser;
import org.eclipse.swt.browser.WindowEvent;
import org.eclipse.swt.layout.FillLayout;
import org.eclipse.swt.widgets.Composite;
import org.eclipse.swt.widgets.Display;
import org.eclipse.swt.widgets.Label;
import org.eclipse.ui.IEditorInput;
import org.eclipse.ui.IEditorSite;
import org.eclipse.ui.IFileEditorInput;
import org.eclipse.ui.IURIEditorInput;
import org.eclipse.ui.IWorkbenchPage;
import org.eclipse.ui.PartInitException;
import org.eclipse.ui.PlatformUI;
import org.eclipse.ui.part.EditorPart;

import com.btfviewer.eclipse.BTFViewerPlugin;
import com.btfviewer.eclipse.bridge.BTFBrowserBridge;
import com.btfviewer.eclipse.bridge.BTFBrowserMessage;
import com.btfviewer.eclipse.resources.ViewerResourceServer;
import com.btfviewer.eclipse.util.JsonUtil;
import com.btfviewer.eclipse.views.BTFPanelView;
import com.btfviewer.eclipse.views.BTFPerspective;

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
    private Display display;
    private final Runnable startupTimeout = this::reportStartupTimeout;
    private IPropertyChangeListener themeListener;
    private final Set<BTFPanelView> pendingPanels = new LinkedHashSet<>();
    private BTFPanelView openingView;
    private boolean traceLoaded;
    private boolean perspectiveOpened;

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
        display = parent.getDisplay();
        boolean windows = "win32".equals(SWT.getPlatform());
        boolean startingBrowser = false;
        try {
            resources = traceFile != null
                    ? new ViewerResourceServer(BTFViewerPlugin.getDefault().getBundle(), traceFile)
                    : new ViewerResourceServer(BTFViewerPlugin.getDefault().getBundle(), localTrace);
            startingBrowser = true;
            browser = new Browser(parent, windows ? SWT.EDGE : SWT.NONE);
            if (windows && !"edge".equals(browser.getBrowserType())) {
                throw new IOException("SWT could not start the Microsoft Edge WebView2 renderer");
            }
            startingBrowser = false;
            bridge = new BTFBrowserBridge(browser, this::onBrowserMessage);
            browser.addOpenWindowListener(this::attachPanelPopup);
            setStatus("Loading viewer...");
            if (!browser.setUrl(resources.viewerUri().toASCIIString())) {
                throw new IOException("SWT Browser rejected the local viewer URL");
            }
            if (!viewerReady) display.timerExec(30_000, startupTimeout);
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
            message.setText(windows && startingBrowser
                    ? "BTFViewer requires the Microsoft Edge WebView2 Runtime on Windows. See the Eclipse Error Log."
                    : "BTFViewer could not initialize the SWT Browser. See the Eclipse Error Log.");
            setStatus("Error");
        }
    }

    private void reportStartupTimeout() {
        if (viewerReady || browser == null || browser.isDisposed()) return;
        String message = "BTFViewer did not start. See the Eclipse Error Log.";
        Composite parent = browser.getParent();
        browser.dispose();
        new Label(parent, SWT.WRAP).setText(message);
        parent.layout();
        resources.close();
        setStatus(message);
        BTFViewerPlugin.log(message, null);
    }

    private void onBrowserMessage(BTFBrowserMessage message) {
        if (browser == null || browser.isDisposed()) return;
        browser.getDisplay().asyncExec(() -> handleBrowserMessage(message));
    }

    private void handleBrowserMessage(BTFBrowserMessage message) {
        if (browser == null || browser.isDisposed()) return;
        switch (message.type()) {
            case "viewerReady" -> {
                viewerReady = true;
                display.timerExec(-1, startupTimeout);
                applyTheme();
                call("openTraceUrl", resources.traceUri().toASCIIString(), traceName);
                setStatus("Loading trace...");
            }
            case "traceLoaded" -> {
                setStatus("Ready");
                if (!traceLoaded) {
                    traceLoaded = true;
                    showTracePerspective();
                }
            }
            case "traceLoadFailed" -> {
                setStatus(statusMessage("Error", message.stringValue("message")));
                BTFViewerPlugin.log("BTF trace load failed: " + traceDescription, null);
            }
            case "statusChanged" -> setStatus(statusMessage(
                    message.stringValue("status"), message.stringValue("message")));
            case "focusTimeline" -> {
                getSite().getShell().forceActive();
                getSite().getPage().activate(this);
            }
            case "revealAnalysis" -> revealAnalysis();
            case "plotOpened" -> {
                getSite().getPage().activate(this);
                browser.execute("document.querySelector('.plot-dialog')?.focus()");
            }
            case "panelOpenFailed" -> {
                String panel = message.stringValue("panel");
                if (openingView != null && openingView.panel().equals(panel)) finishPanelRequest();
            }
            default -> { /* POC receives and validates future messages but has no native action. */ }
        }
    }

    private void showTracePerspective() {
        IWorkbenchPage page = getSite().getPage();
        if (!traceLoaded || perspectiveOpened || page.getActiveEditor() != this) return;
        perspectiveOpened = true;
        page.setPerspective(PlatformUI.getWorkbench().getPerspectiveRegistry().findPerspectiveWithId(BTFPerspective.ID));
        for (String id : new String[] { BTFPanelView.ANALYSIS_ID, BTFPanelView.CPU_ID }) {
            if (page.findView(id) instanceof BTFPanelView view) view.refresh();
        }
    }

    private void revealAnalysis() {
        IWorkbenchPage page = getSite().getPage();
        if (!traceLoaded || page.getActiveEditor() != this) return;
        try {
            if (page.showView(BTFPanelView.ANALYSIS_ID) instanceof BTFPanelView view) view.refresh();
        } catch (PartInitException error) {
            BTFViewerPlugin.log("Unable to reveal BTF Analysis", error);
        }
    }

    public void requestPanel(BTFPanelView view) {
        if (!traceLoaded || view == openingView) return;
        pendingPanels.add(view);
        openNextPanel();
    }

    private void openNextPanel() {
        if (openingView != null || browser == null || browser.isDisposed()) return;
        while (!pendingPanels.isEmpty()) {
            BTFPanelView view = pendingPanels.iterator().next();
            pendingPanels.remove(view);
            if (!view.canAttach(this)) continue;
            openingView = view;
            call("openPanel", view.panel());
            display.timerExec(10_000, panelTimeout);
            return;
        }
    }

    private final Runnable panelTimeout = this::finishPanelRequest;

    private void finishPanelRequest() {
        display.timerExec(-1, panelTimeout);
        openingView = null;
        display.asyncExec(this::openNextPanel);
    }

    private void attachPanelPopup(WindowEvent event) {
        BTFPanelView view = openingView;
        if (view == null) return;
        event.required = true;
        try {
            if (view.canAttach(this)) {
                event.browser = view.attach(() -> {
                    if (browser != null && !browser.isDisposed()) call("returnPanel", view.panel());
                });
                event.browser.addCloseWindowListener(closeEvent -> display.asyncExec(() -> {
                    if (!closeEvent.widget.isDisposed()) view.clearBrowser();
                }));
            }
        } catch (SWTError | RuntimeException error) {
            BTFViewerPlugin.log("Unable to open BTFViewer panel: " + view.panel(), error);
        } finally {
            finishPanelRequest();
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
        if (browser != null && !browser.isDisposed()) {
            browser.setFocus();
            if (traceLoaded && !perspectiveOpened) {
                display.asyncExec(() -> {
                    if (browser != null && !browser.isDisposed()) showTracePerspective();
                });
            }
        }
    }

    @Override public boolean isDirty() { return false; }
    @Override public boolean isSaveAsAllowed() { return false; }
    @Override public void doSave(org.eclipse.core.runtime.IProgressMonitor monitor) {}
    @Override public void doSaveAs() {}

    @Override
    public void dispose() {
        openingView = null;
        pendingPanels.clear();
        if (display != null && !display.isDisposed()) {
            display.timerExec(-1, startupTimeout);
            display.timerExec(-1, panelTimeout);
        }
        if (themeListener != null) {
            PlatformUI.getWorkbench().getThemeManager().removePropertyChangeListener(themeListener);
            themeListener = null;
        }
        if (browser != null && !browser.isDisposed() && bridge != null && !bridge.isDisposed()) {
            bridge.dispose();
        }
        if (resources != null) resources.close();
        bridge = null;
        resources = null;
        browser = null;
        super.dispose();
    }
}
