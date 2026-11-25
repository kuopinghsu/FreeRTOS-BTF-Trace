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

        // The wildcard perspective extension supplies the two trace panes.
        IFolderLayout explorer = layout.createFolder(
                ID + ".explorer", IPageLayout.LEFT, 0.25f, editor);
        explorer.addView(IPageLayout.ID_PROJECT_EXPLORER);
        addAvailableViews(explorer, "org.eclipse.cdt.ui.CView", IPageLayout.ID_OUTLINE);

        // Only the platform action set is guaranteed; the CDT one is optional.
        layout.addActionSet(IPageLayout.ID_NAVIGATE_ACTION_SET);

        layout.addShowViewShortcut(BTFPanelView.ANALYSIS_ID);
        layout.addShowViewShortcut(BTFPanelView.CPU_ID);
        addAvailableViewShortcuts(layout,
                IPageLayout.ID_PROJECT_EXPLORER, "org.eclipse.cdt.ui.CView",
                IPageLayout.ID_PROBLEM_VIEW, IPageLayout.ID_TASK_LIST,
                "org.eclipse.ui.console.ConsoleView", IPageLayout.ID_PROP_SHEET,
                IPageLayout.ID_OUTLINE);

        // Xplorer and CDT ids are absent on a plain Eclipse Platform, so every
        // shortcut is filtered through the registry before being added.
        addAvailablePerspectiveShortcuts(layout,
                "org.eclipse.cdt.ui.CPerspective",
                "org.eclipse.debug.ui.DebugPerspective",
                "com.tensilica.xide.trace.ui.TracePerspective",
                "org.eclipse.ui.resourcePerspective");
    }

    private void addAvailableViewShortcuts(IPageLayout layout, String... ids) {
        var registry = PlatformUI.getWorkbench().getViewRegistry();
        for (String id : ids) {
            if (registry != null && registry.find(id) != null) {
                layout.addShowViewShortcut(id);
            }
        }
    }

    private void addAvailablePerspectiveShortcuts(IPageLayout layout, String... ids) {
        var registry = PlatformUI.getWorkbench().getPerspectiveRegistry();
        for (String id : ids) {
            if (registry != null && registry.findPerspectiveWithId(id) != null) {
                layout.addPerspectiveShortcut(id);
            }
        }
    }

    private void addAvailableViews(IFolderLayout folder, String... ids) {
        var registry = PlatformUI.getWorkbench().getViewRegistry();
        for (String id : ids) {
            if (registry != null && registry.find(id) != null) {
                folder.addView(id);
            }
        }
    }
}
