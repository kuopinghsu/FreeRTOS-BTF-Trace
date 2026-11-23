package com.btfviewer.eclipse.views;

import org.eclipse.ui.IFolderLayout;
import org.eclipse.ui.IPageLayout;
import org.eclipse.ui.IPerspectiveFactory;
import org.eclipse.ui.PlatformUI;

public final class BTFPerspective implements IPerspectiveFactory {
    public static final String ID = "com.btfviewer.eclipse.perspective";

    @Override
    public void createInitialLayout(IPageLayout layout) {
        String editor = layout.getEditorArea();
        IFolderLayout bottom = layout.createFolder(ID + ".bottom", IPageLayout.BOTTOM, 0.76f, editor);
        bottom.addView(BTFPanelView.CPU_ID);
        addAvailableViews(bottom, IPageLayout.ID_PROBLEM_VIEW, IPageLayout.ID_TASK_LIST,
                "org.eclipse.ui.console.ConsoleView", IPageLayout.ID_PROP_SHEET);

        IFolderLayout side = layout.createFolder(ID + ".side", IPageLayout.RIGHT, 0.75f, editor);
        side.addView(BTFPanelView.ANALYSIS_ID);
        addAvailableViews(side, IPageLayout.ID_OUTLINE, "org.eclipse.mylyn.tasks.ui.views.tasks");

        layout.addShowViewShortcut(BTFPanelView.ANALYSIS_ID);
        layout.addShowViewShortcut(BTFPanelView.CPU_ID);
    }

    private void addAvailableViews(IFolderLayout folder, String... ids) {
        var registry = PlatformUI.getWorkbench().getViewRegistry();
        for (String id : ids) {
            if (registry.find(id) != null) folder.addView(id);
        }
    }
}
