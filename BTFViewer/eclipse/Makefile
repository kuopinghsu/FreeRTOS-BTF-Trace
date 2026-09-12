PLUGIN := com.btfviewer.eclipse
VIEWER := ../builds/btf_viewer.html
EMBEDDED := $(PLUGIN)/web/btf_viewer.html
PLUGIN_VERSION ?= 0.1.0
ECLIPSE_HOME ?= /Applications/Eclipse.app/Contents/Eclipse
ECLIPSE_PLUGINS ?= $(ECLIPSE_HOME)/plugins
BUILDS := ../builds
PACKAGE_STAGE := $(BUILDS)/.eclipse-plugin-stage
PACKAGE_MANIFEST := $(BUILDS)/.eclipse-plugin-manifest.mf
PLUGIN_JAR := $(BUILDS)/$(PLUGIN)_$(PLUGIN_VERSION).jar
LEGACY_DROPINS_ZIP := $(BUILDS)/$(PLUGIN)_$(PLUGIN_VERSION)-dropins.zip
PLUGIN_SOURCES := $(shell find $(PLUGIN)/src -name '*.java' -print)

.PHONY: sync-viewer check-viewer package check-package clean-package

sync-viewer: $(VIEWER)
	mkdir -p $(dir $(EMBEDDED))
	cp $(VIEWER) $(EMBEDDED)

check-viewer:
	cmp $(VIEWER) $(EMBEDDED)

package: sync-viewer check-viewer
	@test -d "$(ECLIPSE_PLUGINS)" || { \
		echo "error: Eclipse plug-ins not found at $(ECLIPSE_PLUGINS)" >&2; \
		echo "Set ECLIPSE_HOME=/path/to/eclipse and retry." >&2; \
		exit 1; \
	}
	rm -f $(LEGACY_DROPINS_ZIP)
	rm -rf $(PACKAGE_STAGE)
	mkdir -p $(PACKAGE_STAGE)
	cp $(PLUGIN)/plugin.xml $(PACKAGE_STAGE)/
	cp -R $(PLUGIN)/icons $(PLUGIN)/web $(PACKAGE_STAGE)/
	sed 's/^Bundle-Version:.*/Bundle-Version: $(PLUGIN_VERSION)/' \
		$(PLUGIN)/META-INF/MANIFEST.MF > $(PACKAGE_MANIFEST)
	javac --release 17 -cp '$(ECLIPSE_PLUGINS)/*' \
		-d $(PACKAGE_STAGE) $(PLUGIN_SOURCES)
	jar --create --file $(PLUGIN_JAR) --manifest $(PACKAGE_MANIFEST) -C $(PACKAGE_STAGE) .
	rm -rf $(PACKAGE_STAGE)
	rm -f $(PACKAGE_MANIFEST)
	$(MAKE) check-package
	@echo "Built $(PLUGIN_JAR)"

check-package:
	@test -f $(PLUGIN_JAR)
	@unzip -p $(PLUGIN_JAR) META-INF/MANIFEST.MF | \
		grep -q '^Bundle-SymbolicName: $(PLUGIN);singleton:=true'
	@unzip -p $(PLUGIN_JAR) META-INF/MANIFEST.MF | \
		grep -q '^Bundle-Version: $(PLUGIN_VERSION)'
	@jar tf $(PLUGIN_JAR) | grep -q '^com/btfviewer/eclipse/editor/BTFEditor.class$$'
	@jar tf $(PLUGIN_JAR) | grep -q '^web/btf_viewer.html$$'
	@echo "OK: Eclipse bundle manifest and plug-in JAR verified"

clean-package:
	rm -rf $(PACKAGE_STAGE)
	rm -f $(PACKAGE_MANIFEST)
	rm -f $(PLUGIN_JAR) $(LEGACY_DROPINS_ZIP)
