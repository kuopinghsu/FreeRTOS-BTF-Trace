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
PLUGIN_ICONS := $(shell find $(PLUGIN)/icons -type f -print)

RESOURCES_CHECK_DIR := $(BUILDS)/.eclipse-resources-check
FULL_CHECK_STAGE := $(BUILDS)/.eclipse-check-stage

.PHONY: sync-viewer check-viewer package package-if-sdk check-package clean-package \
	check-eclipse-resources check-eclipse

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

# Opportunistic rebuild used by `make` at the repo root: only touches the JAR
# when the web viewer, plugin.xml, icons, sources, or manifest actually
# changed since it was last packaged (plain file-mtime prerequisites, same
# idiom as $(OUT) in the top-level Makefile), and skips quietly - without
# failing the build - when no Eclipse SDK is installed. `make eclipse-package`
# (the `package` target above) is the explicit, hard-failing equivalent for
# when you specifically want the plug-in and expect Eclipse to be present.
$(PLUGIN_JAR): $(VIEWER) $(PLUGIN)/plugin.xml $(PLUGIN_ICONS) $(PLUGIN_SOURCES) \
		$(PLUGIN)/META-INF/MANIFEST.MF
	@if [ ! -d "$(ECLIPSE_PLUGINS)" ]; then \
		echo "SKIP: Eclipse plug-in rebuild — no Eclipse SDK at $(ECLIPSE_PLUGINS)."; \
		echo "      Set ECLIPSE_HOME=/path/to/eclipse, then run: make -C BTFViewer eclipse-package"; \
		exit 0; \
	fi; \
	$(MAKE) package

package-if-sdk: $(PLUGIN_JAR)

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

# Fail if the committed plug-in JAR's embedded resources or class list have
# drifted from current sources — catches "changed plugin.xml/icons/web viewer
# or added a .java file but forgot to re-run eclipse-package" before commit.
# Uses only unzip (no javac/Eclipse SDK), so it always runs in CI. Compares
# against whatever is currently in $(VIEWER) (does not rebuild web itself) —
# run `make -C BTFViewer web` first if it's stale.
check-eclipse-resources:
	@test -f $(PLUGIN_JAR) || { \
		echo "error: $(PLUGIN_JAR) missing — run: make -C BTFViewer eclipse-package" >&2; exit 1; }
	@test -f $(VIEWER) || { \
		echo "error: $(VIEWER) missing — run: make -C BTFViewer web" >&2; exit 1; }
	@rm -rf $(RESOURCES_CHECK_DIR)
	@mkdir -p $(RESOURCES_CHECK_DIR)
	@unzip -q -o $(PLUGIN_JAR) -d $(RESOURCES_CHECK_DIR)
	@ok=1; \
	if ! cmp -s $(RESOURCES_CHECK_DIR)/web/btf_viewer.html $(VIEWER); then \
		echo "error: packaged web/btf_viewer.html is stale" >&2; ok=0; \
	fi; \
	if ! cmp -s $(RESOURCES_CHECK_DIR)/plugin.xml $(PLUGIN)/plugin.xml; then \
		echo "error: packaged plugin.xml is stale" >&2; ok=0; \
	fi; \
	for f in $$(cd $(PLUGIN)/icons && find . -type f); do \
		if ! cmp -s $(RESOURCES_CHECK_DIR)/icons/$$f $(PLUGIN)/icons/$$f; then \
			echo "error: packaged icons/$$f is stale" >&2; ok=0; \
		fi; \
	done; \
	ver=$$(unzip -p $(PLUGIN_JAR) META-INF/MANIFEST.MF | tr -d '\r' | sed -n 's/^Bundle-Version: //p'); \
	if [ "$$ver" != "$(PLUGIN_VERSION)" ]; then \
		echo "error: packaged Bundle-Version ($$ver) != PLUGIN_VERSION ($(PLUGIN_VERSION))" >&2; ok=0; \
	fi; \
	for src in $(PLUGIN_SOURCES); do \
		rel=$${src#$(PLUGIN)/src/}; \
		cls=$${rel%.java}.class; \
		if [ ! -f $(RESOURCES_CHECK_DIR)/$$cls ]; then \
			echo "error: no compiled class for $$src ($$cls missing from JAR)" >&2; ok=0; \
		fi; \
	done; \
	rm -rf $(RESOURCES_CHECK_DIR); \
	if [ "$$ok" = "1" ]; then \
		echo "OK: $(PLUGIN_JAR) resources match current sources"; \
	else \
		echo "Run: make -C BTFViewer eclipse-package" >&2; exit 1; \
	fi

# Full freshness gate: recompile every .java source against the same Eclipse
# SDK classpath used by `package`, then diff each class file's bytecode
# against the one embedded in the committed JAR. Needs a real Eclipse
# SDK/PDE install (see eclipse-package's ECLIPSE_HOME) - skips with a clear
# message when unavailable (e.g. on CI runners), matching check-web's
# CI-vs-local split. On a machine with Eclipse installed, a non-zero exit
# here is a real freshness failure, not a flake.
check-eclipse: check-eclipse-resources
	@if [ ! -d "$(ECLIPSE_PLUGINS)" ]; then \
		echo "SKIP: check-eclipse — no Eclipse SDK at $(ECLIPSE_PLUGINS)."; \
		echo "      Set ECLIPSE_HOME=/path/to/eclipse to run the full rebuild-and-diff gate."; \
		exit 0; \
	fi; \
	rm -rf $(FULL_CHECK_STAGE); \
	mkdir -p $(FULL_CHECK_STAGE); \
	javac --release 17 -cp '$(ECLIPSE_PLUGINS)/*' \
		-d $(FULL_CHECK_STAGE) $(PLUGIN_SOURCES); \
	ok=1; \
	for cls in $$(cd $(FULL_CHECK_STAGE) && find com -name '*.class'); do \
		if ! unzip -p $(PLUGIN_JAR) $$cls 2>/dev/null | cmp -s - $(FULL_CHECK_STAGE)/$$cls; then \
			echo "error: compiled $$cls differs from the committed JAR" >&2; ok=0; \
		fi; \
	done; \
	rm -rf $(FULL_CHECK_STAGE); \
	if [ "$$ok" = "1" ]; then \
		echo "OK: $(PLUGIN_JAR) classes match a fresh rebuild"; \
	else \
		echo "Run: make -C BTFViewer eclipse-package" >&2; exit 1; \
	fi
