# BTF Viewer — development and release build
#
# Edit btf_viewer_pkg/ then regenerate the single-file release:
#   make -C BTFViewer          # same as: make -C BTFViewer bundle
#   make -C BTFViewer check-bundle

PYTHON ?= python3
TRACE ?= ../tracedata/example.btf
BUILDS := builds
OUT := $(BUILDS)/btf_viewer.py

.DEFAULT_GOAL := bundle

.PHONY: bundle extract check-bundle

bundle: web
	mkdir -p $(BUILDS)
	$(PYTHON) scripts/bundle_viewer.py -o $(OUT)
	$(PYTHON) -m py_compile $(OUT)
	$(PYTHON) $(OUT) info $(TRACE)

web:
	make -C web

# One-shot migration: split a hand-edited monolith into btf_viewer_pkg/.
# Input must not be a generated btf_viewer.py — use git history or a backup.
extract:
	$(PYTHON) scripts/extract_monolith.py

# Fail if builds/btf_viewer.py drifts from package sources (CI / pre-commit).
check-bundle: bundle
	git diff --exit-code $(OUT)
