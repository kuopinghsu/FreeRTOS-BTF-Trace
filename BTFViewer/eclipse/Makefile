# Windows: recipes are POSIX sh (mkdir -p, rm -f, VAR=x cmd). Without sh.exe on
# PATH (e.g. make run from PowerShell) GNU make falls back to cmd.exe, so pin
# Git for Windows' sh. Override with GIT_SH=... if Git lives elsewhere.
ifeq ($(OS),Windows_NT)
GIT_SH ?= C:/Program Files/Git/bin/sh.exe
SHELL := $(GIT_SH)
GIT_USR_BIN ?= $(subst /bin/sh.exe,/usr/bin,$(GIT_SH))
export PATH := $(GIT_USR_BIN);$(PATH)
# Run even simple recipes through sh so they use the exported tool path.
.SHELLFLAGS := -e -c
JAVA_EXE_SUFFIX := .exe
# A 32-bit make process sees the x86 Program Files directory in ProgramFiles.
JDK_PROGRAM_FILES := $(subst \,/,$(or $(ProgramW6432),$(ProgramFiles)))
WINDOWS_JDK_CANDIDATES = "$(JDK_PROGRAM_FILES)/Java/latest" \
	"$(JDK_PROGRAM_FILES)/Java"/jdk-* \
	"$(JDK_PROGRAM_FILES)/Microsoft"/jdk-* \
	"$(JDK_PROGRAM_FILES)/Eclipse Adoptium"/jdk-*
endif
JDK_BIN := $(shell \
	for home in "$(subst \,/,$(subst ",,$(JAVA_HOME)))" PATH $(WINDOWS_JDK_CANDIDATES); do \
		if [ "$$home" = PATH ]; then \
			if command -v javac >/dev/null && command -v jar >/dev/null; then break; fi; \
		elif [ -n "$$home" ] && [ -x "$$home/bin/javac$(JAVA_EXE_SUFFIX)" ] && [ -x "$$home/bin/jar$(JAVA_EXE_SUFFIX)" ]; then \
			printf '%s/bin/' "$$home"; break; \
		fi; \
	done)
JAVAC := $(if $(JDK_BIN),$(JDK_BIN)javac$(JAVA_EXE_SUFFIX),javac)
JAR := $(if $(JDK_BIN),$(JDK_BIN)jar$(JAVA_EXE_SUFFIX),jar)
CHECK_JDK = command -v "$(JAVAC)" >/dev/null && command -v "$(JAR)" >/dev/null || { \
	printf '%s\n' 'error: JDK tools javac and jar are required. Set JAVA_HOME to a JDK 17 or newer, or add its bin directory to PATH.' >&2; \
	exit 1; \
}

PLUGIN := com.btfviewer.eclipse
VIEWER := ../builds/btf_viewer.html
EMBEDDED := $(PLUGIN)/web/btf_viewer.html
PLUGIN_VERSION ?= 0.1.0
ifneq ($(OS),Windows_NT)
ifeq ($(shell uname -s),Darwin)
ECLIPSE_HOME ?= /Applications/Eclipse.app/Contents/Eclipse
endif
endif
ECLIPSE_PLUGINS ?= $(if $(strip $(ECLIPSE_HOME)),$(ECLIPSE_HOME)/plugins)
ECLIPSE_SDK_REASON = $(if $(strip $(ECLIPSE_PLUGINS)),Eclipse plug-ins not found at $(ECLIPSE_PLUGINS),Eclipse installation directory not configured)
ifeq ($(OS),Windows_NT)
ECLIPSE_SDK_HINT = Set ECLIPSE_HOME to the Eclipse folder that contains plugins (for example "ECLIPSE_HOME=C:/path/to/eclipse").
else
ECLIPSE_SDK_HINT = Set ECLIPSE_HOME to the Eclipse folder that contains plugins.
endif
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

package: sync-viewer
	$(MAKE) check-viewer
	@test -d "$(ECLIPSE_PLUGINS)" || { \
		printf '%s\n' 'error: $(ECLIPSE_SDK_REASON).' '$(ECLIPSE_SDK_HINT)' >&2; \
		exit 1; \
	}
	@$(CHECK_JDK)
	rm -f $(LEGACY_DROPINS_ZIP)
	rm -rf $(PACKAGE_STAGE)
	mkdir -p $(PACKAGE_STAGE)
	cp $(PLUGIN)/plugin.xml $(PACKAGE_STAGE)/
	cp -R $(PLUGIN)/icons $(PLUGIN)/web $(PACKAGE_STAGE)/
	sed 's/^Bundle-Version:.*/Bundle-Version: $(PLUGIN_VERSION)/' \
		$(PLUGIN)/META-INF/MANIFEST.MF > $(PACKAGE_MANIFEST)
	@version=$$("$(JAVAC)" -version 2>&1 | tr -d '\r' | sed -n 's/^javac //p'); \
	test -n "$$version" && printf 'BTF-Javac-Version: %s\n' "$$version" >> $(PACKAGE_MANIFEST)
	"$(JAVAC)" --release 17 -cp '$(ECLIPSE_PLUGINS)/*' \
		-d $(PACKAGE_STAGE) $(PLUGIN_SOURCES)
	"$(JAR)" --create --file $(PLUGIN_JAR) --manifest $(PACKAGE_MANIFEST) -C $(PACKAGE_STAGE) .
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
		printf '%s\n' 'SKIP: Eclipse plug-in rebuild. $(ECLIPSE_SDK_REASON).' '      $(ECLIPSE_SDK_HINT)' '      Then run: make -C BTFViewer eclipse-package'; \
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
	@"$(JAR)" tf $(PLUGIN_JAR) | grep -q '^com/btfviewer/eclipse/editor/BTFEditor.class$$'
	@"$(JAR)" tf $(PLUGIN_JAR) | grep -q '^web/btf_viewer.html$$'
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

# Recompile against the configured Eclipse SDK and verify the class list.
# Compare bytecode when the compiler version matches the packaged version.
check-eclipse: check-eclipse-resources
	@set -e; \
	if [ ! -d "$(ECLIPSE_PLUGINS)" ]; then \
		printf '%s\n' 'SKIP: check-eclipse. $(ECLIPSE_SDK_REASON).' '      $(ECLIPSE_SDK_HINT)'; \
		exit 0; \
	fi; \
	$(CHECK_JDK); \
	rm -rf $(FULL_CHECK_STAGE); \
	mkdir -p $(FULL_CHECK_STAGE); \
	trap 'rm -rf $(FULL_CHECK_STAGE)' 0; \
	"$(JAVAC)" --release 17 -cp '$(ECLIPSE_PLUGINS)/*' \
		-d $(FULL_CHECK_STAGE) $(PLUGIN_SOURCES); \
	(cd $(FULL_CHECK_STAGE) && find com -name '*.class' | LC_ALL=C sort) > $(FULL_CHECK_STAGE)/compiled.txt; \
	"$(JAR)" tf $(PLUGIN_JAR) | tr -d '\r' | sed -n '/^com\/.*\.class$$/p' | LC_ALL=C sort > $(FULL_CHECK_STAGE)/packaged.txt; \
	if ! cmp -s $(FULL_CHECK_STAGE)/compiled.txt $(FULL_CHECK_STAGE)/packaged.txt; then \
		echo "error: packaged class list differs from the fresh rebuild" >&2; exit 1; \
	fi; \
	version=$$("$(JAVAC)" -version 2>&1 | tr -d '\r' | sed -n 's/^javac //p'); \
	packaged=$$(unzip -p $(PLUGIN_JAR) META-INF/MANIFEST.MF | tr -d '\r' | sed -n 's/^BTF-Javac-Version: //p'); \
	if [ -z "$$packaged" ] || [ "$$version" != "$$packaged" ]; then \
		echo "OK: recompiled and verified class list. Bytecode comparison skipped because compiler versions differ or are unknown."; \
		exit 0; \
	fi; \
	ok=1; \
	while IFS= read -r cls; do \
		if ! unzip -p $(PLUGIN_JAR) $$cls 2>/dev/null | cmp -s - $(FULL_CHECK_STAGE)/$$cls; then \
			echo "error: compiled $$cls differs from the committed JAR" >&2; ok=0; \
		fi; \
	done < $(FULL_CHECK_STAGE)/compiled.txt; \
	if [ "$$ok" = "1" ]; then \
		echo "OK: $(PLUGIN_JAR) classes match a fresh rebuild"; \
	else \
		echo "Run: make -C BTFViewer eclipse-package" >&2; exit 1; \
	fi
