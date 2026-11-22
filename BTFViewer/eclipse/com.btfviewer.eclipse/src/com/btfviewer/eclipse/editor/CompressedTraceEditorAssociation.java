package com.btfviewer.eclipse.editor;

import java.net.URI;
import java.util.Locale;

import org.eclipse.core.runtime.CoreException;
import org.eclipse.core.runtime.content.IContentType;
import org.eclipse.ui.IEditorDescriptor;
import org.eclipse.ui.IEditorInput;
import org.eclipse.ui.IFileEditorInput;
import org.eclipse.ui.IURIEditorInput;
import org.eclipse.ui.PlatformUI;
import org.eclipse.ui.ide.IDE;
import org.eclipse.ui.ide.IEditorAssociationOverride;

/** Selects the trace editor when Eclipse routes a compressed trace as a generic archive. */
public final class CompressedTraceEditorAssociation implements IEditorAssociationOverride {
    @Override
    public IEditorDescriptor overrideDefaultEditor(String fileName, IContentType contentType,
            IEditorDescriptor current) {
        IEditorDescriptor viewer = findTraceEditor(fileName);
        return viewer == null ? current : viewer;
    }

    @Override
    public IEditorDescriptor overrideDefaultEditor(IEditorInput input, IContentType contentType,
            IEditorDescriptor current) {
        if (input instanceof IFileEditorInput fileInput) {
            try {
                if (fileInput.getFile().getPersistentProperty(IDE.EDITOR_KEY) != null) {
                    return current;
                }
            } catch (CoreException error) {
                return current;
            }
        }
        return overrideDefaultEditor(supportedInputName(input), contentType, current);
    }

    @Override
    public IEditorDescriptor[] overrideEditors(String fileName, IContentType contentType,
            IEditorDescriptor[] editors) {
        IEditorDescriptor viewer = findTraceEditor(fileName);
        if (viewer == null) {
            return editors;
        }
        for (IEditorDescriptor editor : editors) {
            if (BTFEditor.EDITOR_ID.equals(editor.getId())) {
                return editors;
            }
        }
        IEditorDescriptor[] result = new IEditorDescriptor[editors.length + 1];
        result[0] = viewer;
        System.arraycopy(editors, 0, result, 1, editors.length);
        return result;
    }

    @Override
    public IEditorDescriptor[] overrideEditors(IEditorInput input, IContentType contentType,
            IEditorDescriptor[] editors) {
        return overrideEditors(supportedInputName(input), contentType, editors);
    }

    private static String supportedInputName(IEditorInput input) {
        if (input instanceof IFileEditorInput) {
            return input.getName();
        }
        if (input instanceof IURIEditorInput uriInput) {
            URI uri = uriInput.getURI();
            if (uri != null && "file".equalsIgnoreCase(uri.getScheme())) {
                return input.getName();
            }
        }
        return null;
    }

    private static IEditorDescriptor findTraceEditor(String fileName) {
        if (fileName == null) {
            return null;
        }
        String name = fileName.toLowerCase(Locale.ROOT);
        if (!name.endsWith(".btf.gz") && !name.endsWith(".btf.bz2") && !name.endsWith(".btf.zip")) {
            return null;
        }
        return PlatformUI.getWorkbench().getEditorRegistry().findEditor(BTFEditor.EDITOR_ID);
    }
}
