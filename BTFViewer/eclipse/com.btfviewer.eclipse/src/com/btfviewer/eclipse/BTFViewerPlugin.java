package com.btfviewer.eclipse;

import org.eclipse.core.runtime.IStatus;
import org.eclipse.core.runtime.Status;
import org.eclipse.ui.plugin.AbstractUIPlugin;
import org.osgi.framework.BundleContext;

public final class BTFViewerPlugin extends AbstractUIPlugin {
    public static final String PLUGIN_ID = "com.btfviewer.eclipse";
    private static BTFViewerPlugin instance;

    @Override
    public void start(BundleContext context) throws Exception {
        super.start(context);
        instance = this;
    }

    @Override
    public void stop(BundleContext context) throws Exception {
        instance = null;
        super.stop(context);
    }

    public static BTFViewerPlugin getDefault() {
        return instance;
    }

    public static void log(String message, Throwable error) {
        BTFViewerPlugin plugin = instance;
        if (plugin != null) {
            plugin.getLog().log(new Status(IStatus.ERROR, PLUGIN_ID, message, error));
        }
    }
}

