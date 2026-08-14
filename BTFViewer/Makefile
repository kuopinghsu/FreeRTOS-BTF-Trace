# BTF Viewer — development and release build
#
#   make -C BTFViewer              # builds web + desktop → builds/btf_viewer.{html,py}
#   make -C BTFViewer bundle       # desktop only
#   make -C BTFViewer web          # web only
#   make -C BTFViewer demo         # guided demo (demo_8cores)
#   make -C BTFViewer check-bundle # desktop parity check (CI)
#   make -C BTFViewer ai-test      # offline AI benchmark (tests/ai)
#   make -C BTFViewer ai-test-live # live suite XML → AI_BENCHMARK.md (AI_CONFIG)

PYTHON ?= python3
TRACE ?= ../tracedata/example-2cores.btf.gz
BUILDS := builds
OUT := $(BUILDS)/btf_viewer.py

# Source trace + output dir for `make update-images` (docs/*.md illustrations).
STATS_TRACE ?= ../tracedata/example-8cores.btf.gz
STATS_IMG_DIR := ../images/stats

# Source trace + output for `make update-images` (Migration & Corridor Inspector).
MIGRATION_TRACE ?= ../tracedata/example-8cores.btf.gz
MIGRATION_IMG := ../images/migration.svg

.DEFAULT_GOAL := all

PANDOC ?= pandoc
DOCS := $(BUILDS)

DEMO_XML ?= demos/demo_8cores/demo_8cores.xml
DEMO_LANG ?=
AI_DATASET ?= tests/ai
AI_FAIL_UNDER ?= 70
AI_CONFIG ?= examples/ai/benchmark.xml
AI_MODELS ?=

.PHONY: all help web bundle check-bundle test test-web test-all ai-test ai-test-live ci doc update-images demo demo-voice

help:
	@echo "BTF Viewer — make targets"
	@echo ""
	@echo "  make              Build web + desktop (default)"
	@echo "  make web          Web viewer only → builds/btf_viewer.html"
	@echo "  make bundle       Desktop bundle only → builds/btf_viewer.py"
	@echo "  make check-bundle Regenerate bundle; fail if it drifts from sources (CI)"
	@echo "  make doc          Convert README.md + WORKFLOWS.md → builds/*.pdf (Eisvogel + XeLaTeX)"
	@echo "  make update-images  Regenerate ../images/stats/*.svg via the desktop CLI"
	@echo "  make demo         Run guided demo via builds/btf_viewer.py (DEMO_XML, DEMO_LANG, --launch)"
	@echo "  make demo-voice   Voice pack status (DEMO_XML). See scripts/demo_voice.py"
	@echo "  make test         Desktop unit tests (QT_QPA_PLATFORM=offscreen)"
	@echo "  make test-web     Web unit tests (node --test)"
	@echo "  make test-all     Desktop + web unit tests"
	@echo "  make ai-test      Offline AI benchmark ($(AI_DATASET); AI_FAIL_UNDER=$(AI_FAIL_UNDER))"
	@echo "  make ai-test-live Live suite XML → AI_BENCHMARK.md (AI_CONFIG=$(AI_CONFIG))"
	@echo "  make ci           test-all + check-bundle (local CI parity)"
	@echo "  make help         Show this help"
	@echo ""
	@echo "Variables: PYTHON=$(PYTHON)  TRACE=$(TRACE)  PANDOC=$(PANDOC)  STATS_TRACE=$(STATS_TRACE)  MIGRATION_TRACE=$(MIGRATION_TRACE)  DEMO_XML=$(DEMO_XML)  DEMO_LANG=$(DEMO_LANG)  AI_DATASET=$(AI_DATASET)  AI_FAIL_UNDER=$(AI_FAIL_UNDER)  AI_CONFIG=$(AI_CONFIG)  AI_MODELS=$(AI_MODELS)"


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

demo: $(OUT)
	$(PYTHON) scripts/demo_runner.py $(DEMO_XML) --launch $(if $(DEMO_LANG),--lang $(DEMO_LANG),)

demo-voice:
	$(PYTHON) scripts/demo_voice.py status $(DEMO_XML)

# Demo launches builds/btf_viewer.py; rebuild when package sources change.
BUNDLE_SRCS := $(wildcard btf_viewer_pkg/*.py) \
	$(wildcard btf_viewer_pkg/mvvm/*.py) \
	scripts/bundle_viewer.py
$(OUT): $(BUNDLE_SRCS)
	$(MAKE) bundle

test-web:
	$(MAKE) -C web test

test-all: test test-web

ai-test: $(OUT)
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) ai-test \
		--dataset $(AI_DATASET) --fail-under $(AI_FAIL_UNDER)

ai-test-live: $(OUT)
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) ai-test \
		--config $(AI_CONFIG) $(if $(AI_MODELS),--models $(AI_MODELS),) \
		--fail-under 0 -o AI_BENCHMARK.md

ci: test-all check-bundle

doc: $(DOCS)/README.pdf $(DOCS)/AI.pdf $(DOCS)/WORKFLOWS.pdf

# Use the vendored Eisvogel template (scripts/eisvogel.latex). Do not pass
# `--template=eisvogel`: pandoc prefers ~/.local/share/pandoc/templates/eisvogel.latex,
# and a 0-byte file there yields an empty .tex and xelatex "no legal \end found".
#
# `-f markdown-blank_before_header`: README.md/AI.md put a `<a id=... name=...>`
# anchor directly above every heading (no blank line, for stable GitHub anchors).
# Pandoc's default +blank_before_header extension then refuses to parse those
# `#`/`##` lines as headings at all — they show up as literal "# Heading" body
# text in the PDF. Disabling the extension restores normal heading rendering.
PANDOC_PDF_FLAGS := --pdf-engine=xelatex \
    --template=scripts/eisvogel.latex \
	--lua-filter scripts/math-codeblock.lua \
	--resource-path=..:. \
	-f markdown-blank_before_header \
	-V mainfont="DejaVu Sans" \
	-V monofont="DejaVu Sans Mono" \
	-V colorlinks=true

$(DOCS)/README.pdf: README.md
	mkdir -p $(DOCS)
	$(PANDOC) $(PANDOC_PDF_FLAGS) -M title="BTF Trace Viewer" $< -o $@

$(DOCS)/AI.pdf: AI.md
	mkdir -p $(DOCS)
	$(PANDOC) $(PANDOC_PDF_FLAGS) -M title="BTF AI Assistant" $< -o $@

$(DOCS)/WORKFLOWS.pdf: WORKFLOWS.md
	mkdir -p $(DOCS)
	$(PANDOC) $(PANDOC_PDF_FLAGS) -M title="BTF Viewer — Analysis Workflows" $< -o $@

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
		-o $(STATS_IMG_DIR)/stats-dispatch-sr0.svg --view plot --metric dispatch --task "SR0[271]"
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-switch-core0.svg --view plot --metric switch_overhead --core Core_0
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(STATS_TRACE) \
		-o $(STATS_IMG_DIR)/stats-concurrency-4.svg --view plot --metric concurrency --active-cores 4
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
	QT_QPA_PLATFORM=offscreen $(PYTHON) $(OUT) snapshot $(MIGRATION_TRACE) \
		-o $(MIGRATION_IMG) --view chord \
		--width 1000 --height 720 --drill-row 0
	@echo "Updated $(MIGRATION_IMG)"

