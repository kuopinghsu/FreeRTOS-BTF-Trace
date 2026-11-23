package com.btfviewer.eclipse.views;

import org.eclipse.ui.IPageLayout;
import org.eclipse.ui.IPerspectiveFactory;

public final class BTFPerspective implements IPerspectiveFactory {
    public static final String ID = "com.btfviewer.eclipse.perspective";

    @Override
    public void createInitialLayout(IPageLayout layout) {
        String editor = layout.getEditorArea();
        layout.addView(BTFPanelView.CPU_ID, IPageLayout.BOTTOM, 0.76f, editor);
        layout.addView(BTFPanelView.ANALYSIS_ID, IPageLayout.LEFT, 0.28f, editor);
        layout.addShowViewShortcut(BTFPanelView.ANALYSIS_ID);
        layout.addShowViewShortcut(BTFPanelView.CPU_ID);
    }
}
