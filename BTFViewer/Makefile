# BTF Viewer — development and release build
#
#   make -C BTFViewer              # builds web + desktop → builds/btf_viewer.{html,py}
#   make -C BTFViewer bundle       # desktop only
#   make -C BTFViewer web          # web only
#   make -C BTFViewer check-bundle # desktop parity check (CI)

PYTHON ?= python3
TRACE ?= ../tracedata/example.btf
BUILDS := builds
OUT := $(BUILDS)/btf_viewer.py

.DEFAULT_GOAL := all

.PHONY: all help web bundle check-bundle test

help:
	@echo "BTF Viewer — make targets"
	@echo ""
	@echo "  make              Build web + desktop (default)"
	@echo "  make web          Web viewer only → builds/btf_viewer.html"
	@echo "  make bundle       Desktop bundle only → builds/btf_viewer.py"
	@echo "  make check-bundle Regenerate bundle; fail if it drifts from sources (CI)"
	@echo "  make test         Desktop unit tests (QT_QPA_PLATFORM=offscreen)"
	@echo "  make help         Show this help"
	@echo ""
	@echo "Variables: PYTHON=$(PYTHON)  TRACE=$(TRACE)"

all: web bundle

web:
	$(MAKE) -C web

bundle:
	mkdir -p $(BUILDS)
	$(PYTHON) scripts/bundle_viewer.py -o $(OUT)
	$(PYTHON) -m py_compile $(OUT)
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) info $(TRACE)

test:
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m unittest discover -s tests -v

# Fail if builds/btf_viewer.py drifts from package sources (CI / pre-commit).
check-bundle: bundle
	git diff --exit-code $(OUT)
