package com.btfviewer.eclipse.views;

import org.eclipse.swt.SWT;
import org.eclipse.swt.browser.Browser;
import org.eclipse.swt.custom.StackLayout;
import org.eclipse.swt.widgets.Composite;
import org.eclipse.swt.widgets.Label;
import org.eclipse.ui.IPartListener2;
import org.eclipse.ui.IEditorPart;
import org.eclipse.ui.IWorkbenchPartReference;
import org.eclipse.ui.part.ViewPart;

import com.btfviewer.eclipse.editor.BTFEditor;

/** Hosts a popup from the active trace editor's SWT Browser. */
public final class BTFPanelView extends ViewPart {
    public static final String ANALYSIS_ID = "com.btfviewer.eclipse.analysis";
    public static final String CPU_ID = "com.btfviewer.eclipse.cpu";

    private Composite parent;
    private Label hint;
    private Browser browser;
    private BTFEditor owner;
    private final StackLayout layout = new StackLayout();
    private final IPartListener2 editorListener = new IPartListener2() {
        @Override
        public void partActivated(IWorkbenchPartReference part) {
            if (part.getPart(false) instanceof IEditorPart || part.getPart(false) == BTFPanelView.this) {
                refresh();
            }
        }

        @Override
        public void partClosed(IWorkbenchPartReference part) {
            refresh();
        }

        @Override
        public void partVisible(IWorkbenchPartReference part) {
            if (part.getPart(false) == BTFPanelView.this) refresh();
        }
    };

    @Override
    public void createPartControl(Composite parent) {
        this.parent = parent;
        parent.setLayout(layout);
        hint = new Label(parent, SWT.WRAP);
        hint.setText("Open a BTF trace to populate this view.");
        layout.topControl = hint;
        getSite().getPage().addPartListener(editorListener);
        refresh();
    }

    public void refresh() {
        parent.getDisplay().asyncExec(() -> {
            if (parent.isDisposed()) return;
            var active = getSite().getPage().getActiveEditor();
            BTFEditor next = active instanceof BTFEditor editor ? editor : null;
            if (owner != next) {
                clearBrowser();
                owner = next;
            }
            if (owner != null && browser == null) owner.requestPanel(this);
        });
    }

    public boolean canAttach(BTFEditor editor) {
        return parent != null && !parent.isDisposed() && owner == editor && browser == null
                && getSite().getPage().getActiveEditor() == editor;
    }

    public String panel() {
        return CPU_ID.equals(getSite().getId()) ? "cpu" : "analysis";
    }

    public Browser attach(String traceName, Runnable onClosed) {
        browser = new Browser(parent, "win32".equals(SWT.getPlatform()) ? SWT.EDGE : SWT.NONE);
        browser.addDisposeListener(event -> {
            browser = null;
            onClosed.run();
        });
        layout.topControl = browser;
        setContentDescription(traceName);
        parent.layout();
        return browser;
    }

    public void clearBrowser() {
        if (browser != null && !browser.isDisposed()) browser.dispose();
        if (hint != null && !hint.isDisposed()) {
            layout.topControl = hint;
            setContentDescription("");
            parent.layout();
        }
    }

    @Override
    public void dispose() {
        getSite().getPage().removePartListener(editorListener);
        clearBrowser();
        owner = null;
        super.dispose();
    }

    @Override
    public void setFocus() {
        if (browser != null && !browser.isDisposed()) browser.setFocus();
    }
}
