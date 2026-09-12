package com.btfviewer.eclipse.bridge;

import java.util.function.Consumer;

import org.eclipse.swt.browser.Browser;
import org.eclipse.swt.browser.BrowserFunction;

import com.btfviewer.eclipse.BTFViewerPlugin;

public final class BTFBrowserBridge extends BrowserFunction {
    public static final String FUNCTION_NAME = "btfviewerEclipseBridge";
    private final Consumer<BTFBrowserMessage> listener;

    public BTFBrowserBridge(Browser browser, Consumer<BTFBrowserMessage> listener) {
        super(browser, FUNCTION_NAME);
        this.listener = listener;
    }

    @Override
    public Object function(Object[] arguments) {
        if (arguments.length != 1 || !(arguments[0] instanceof String json)) return Boolean.FALSE;
        try {
            listener.accept(BTFBrowserMessage.parse(json));
            return Boolean.TRUE;
        } catch (IllegalArgumentException error) {
            BTFViewerPlugin.log("Rejected browser bridge message", error);
            return Boolean.FALSE;
        }
    }
}

