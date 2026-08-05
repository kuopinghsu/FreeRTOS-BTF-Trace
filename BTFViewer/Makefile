# BTF Viewer — development and release build
#
#   make -C BTFViewer              # builds web + desktop → builds/btf_viewer.{html,py}
#   make -C BTFViewer bundle       # desktop only
#   make -C BTFViewer web          # web only
#   make -C BTFViewer check-bundle # desktop parity check (CI)

PYTHON ?= python3
TRACE ?= ../tracedata/example-2cores.btf.gz
BUILDS := builds
OUT := $(BUILDS)/btf_viewer.py

# Source trace + output dir for `make update-images` (docs/*.md illustrations).
STATS_TRACE ?= ../tracedata/example-8cores.btf.gz
STATS_IMG_DIR := ../images/stats

# Source trace + output dir for `make update-images` (Migration Heatmap
# illustrations in README.md).
HEATMAP_TRACE ?= ../tracedata/example-4cores.btf.gz
HEATMAP_IMG_DIR := ../images

# Source trace for `make update-images` (Migration Chord Diagram
# illustration in README.md); more cores makes for a more illustrative diagram.
CHORD_TRACE ?= ../tracedata/example-8cores.btf.gz

.DEFAULT_GOAL := all

PANDOC ?= pandoc
DOCS := $(BUILDS)

.PHONY: all help web bundle check-bundle test test-web test-all ci doc update-images

help:
	@echo "BTF Viewer — make targets"
	@echo ""
	@echo "  make              Build web + desktop (default)"
	@echo "  make web          Web viewer only → builds/btf_viewer.html"
	@echo "  make bundle       Desktop bundle only → builds/btf_viewer.py"
	@echo "  make check-bundle Regenerate bundle; fail if it drifts from sources (CI)"
	@echo "  make doc          Convert README.md + WORKFLOWS.md → builds/*.pdf"
	@echo "  make update-images  Regenerate ../images/stats/*.svg via the desktop CLI"
	@echo "  make test         Desktop unit tests (QT_QPA_PLATFORM=offscreen)"
	@echo "  make test-web     Web unit tests (node --test)"
	@echo "  make test-all     Desktop + web unit tests"
	@echo "  make ci           test-all + check-bundle (local CI parity)"
	@echo "  make help         Show this help"
	@echo ""
	@echo "Variables: PYTHON=$(PYTHON)  TRACE=$(TRACE)  PANDOC=$(PANDOC)  STATS_TRACE=$(STATS_TRACE)  HEATMAP_TRACE=$(HEATMAP_TRACE)  CHORD_TRACE=$(CHORD_TRACE)"


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

doc: $(DOCS)/README.pdf $(DOCS)/WORKFLOWS.pdf

PANDOC_PDF_FLAGS := --pdf-engine=xelatex \
    --template=eisvogel \
	--lua-filter scripts/math-codeblock.lua \
	-V mainfont="DejaVu Sans" \
	-V monofont="DejaVu Sans Mono"

$(DOCS)/%.pdf: %.md
	mkdir -p $(DOCS)
	$(PANDOC) $(PANDOC_PDF_FLAGS) $< -o $@

# Fail if builds/btf_viewer.py drifts from package sources (CI / pre-commit).
check-bundle: bundle
	git diff --exit-code $(OUT)

# Regenerate the statistics distribution plots + task-priority timeline crop
# used as illustrations in README.md / WORKFLOWS.md / btf-viewer-slides.md,
# headlessly via the desktop CLI `snapshot` command (Statistics -> click row
# equivalents), sourced from STATS_TRACE (default: example-8cores.btf).
update-images: bundle
	mkdir -p $(STATS_IMG_DIR)
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-tick.svg --view plot --metric tick
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-exec-cs11.svg --view plot --metric exec --task "CS[11]"
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-block-cs11.svg --view plot --metric block --task "CS[11]"
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-inter-cs11.svg --view plot --metric inter --task "CS[11]"
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-mig-dwell-cs22.svg --view plot --metric mig_dwell --task "CS[22]"
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-mig-rate-cs22.svg --view plot --metric mig_rate --task "CS[22]"
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-mig-gap-cs22.svg --view plot --metric mig_gap --task "CS[22]"
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-pair-gap-c5-c7.svg --view plot --metric pair_gap \
		--from-core Core_5 --to-core Core_7
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-pair-rate-c5-c7.svg --view plot --metric pair_rate \
		--from-core Core_5 --to-core Core_7
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-preempt-cs24-cs25.svg --view plot --metric preempt \
		--task "CS[24]" --preemptor "CS[25]"
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-priority-low.svg --view plot --metric priority --task "Low[266]"
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-interval-1.svg --view plot --metric interval --interval-id 1
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-tag0.svg --view plot --metric tag --channel tag0_event
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/tasks-priority-low.svg --view timeline --task "Low[266]" \
		--lo 3042000 --hi 3359000
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/tasks-cpu-load-cs22.svg --view timeline --view-mode task \
		--task "CS[22]" --cpu-load --height 900 \
		--lo 1464000 --hi 1764000
	@echo "Updated $(STATS_IMG_DIR) from $(STATS_TRACE)"
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(HEATMAP_TRACE) \
		-o $(HEATMAP_IMG_DIR)/heatmap-pairs.svg --view heatmap
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(HEATMAP_TRACE) \
		-o $(HEATMAP_IMG_DIR)/heatmap-tasks.svg --view heatmap --drill-row 0 --drill-bin 0
	@echo "Updated $(HEATMAP_IMG_DIR)/heatmap-{pairs,tasks}.svg from $(HEATMAP_TRACE)"
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(CHORD_TRACE) \
		-o $(HEATMAP_IMG_DIR)/migration-chord.svg --view chord
	@echo "Updated $(HEATMAP_IMG_DIR)/migration-chord.svg from $(CHORD_TRACE)"

