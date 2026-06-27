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

.PHONY: all web bundle check-bundle test

all: web bundle

web:
	$(MAKE) -C web

bundle:
	mkdir -p $(BUILDS)
	$(PYTHON) scripts/bundle_viewer.py -o $(OUT)
	$(PYTHON) -m py_compile $(OUT)
	$(PYTHON) $(OUT) info $(TRACE)

test:
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m unittest discover -s tests -v

# Fail if builds/btf_viewer.py drifts from package sources (CI / pre-commit).
check-bundle: bundle
	git diff --exit-code $(OUT)
