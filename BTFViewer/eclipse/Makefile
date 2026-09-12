PLUGIN := com.btfviewer.eclipse
VIEWER := ../builds/btf_viewer.html
EMBEDDED := $(PLUGIN)/web/btf_viewer.html

.PHONY: sync-viewer check-viewer

sync-viewer: $(VIEWER)
	cp $(VIEWER) $(EMBEDDED)

check-viewer:
	cmp $(VIEWER) $(EMBEDDED)

