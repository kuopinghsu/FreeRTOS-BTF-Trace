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

PANDOC ?= pandoc
DOCS := $(BUILDS)

.PHONY: all help web bundle check-bundle test test-web test-all ci doc

help:
	@echo "BTF Viewer — make targets"
	@echo ""
	@echo "  make              Build web + desktop (default)"
	@echo "  make web          Web viewer only → builds/btf_viewer.html"
	@echo "  make bundle       Desktop bundle only → builds/btf_viewer.py"
	@echo "  make check-bundle Regenerate bundle; fail if it drifts from sources (CI)"
	@echo "  make doc          Convert README.md + APPLICATION.md → builds/*.pdf"
	@echo "  make test         Desktop unit tests (QT_QPA_PLATFORM=offscreen)"
	@echo "  make test-web     Web unit tests (node --test)"
	@echo "  make test-all     Desktop + web unit tests"
	@echo "  make ci           test-all + check-bundle (local CI parity)"
	@echo "  make help         Show this help"
	@echo ""
	@echo "Variables: PYTHON=$(PYTHON)  TRACE=$(TRACE)  PANDOC=$(PANDOC)"

all: web bundle

web:
	$(MAKE) -C web

bundle:
	mkdir -p $(BUILDS)
	$(PYTHON) scripts/bundle_viewer.py -o $(OUT)
	$(PYTHON) -m py_compile $(OUT)
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) info $(TRACE)

test:
	QT_QPA_PLATFORM=offscreen \
	QT_LOGGING_RULES='qt.qpa.fonts.warning=false;qt.qpa.offscreen.warning=false' \
	$(PYTHON) -m unittest discover -s tests -v

test-web:
	$(MAKE) -C web test

test-all: test test-web

ci: test-all check-bundle

doc: $(DOCS)/README.pdf $(DOCS)/APPLICATION.pdf

PANDOC_PDF_FLAGS := --pdf-engine=xelatex \
	--lua-filter scripts/math-codeblock.lua \
	-V mainfont="DejaVu Sans" \
	-V monofont="DejaVu Sans Mono"

$(DOCS)/%.pdf: %.md
	mkdir -p $(DOCS)
	$(PANDOC) $(PANDOC_PDF_FLAGS) $< -o $@
	cp $@ docs/.

# Fail if builds/btf_viewer.py drifts from package sources (CI / pre-commit).
check-bundle: bundle
	git diff --exit-code $(OUT)
