# BTF Viewer — development and release build
#
#   make -C BTFViewer              # builds web + desktop → builds/btf_viewer.{html,py}
#   make -C BTFViewer bundle       # desktop only
#   make -C BTFViewer web          # web only
#   make -C BTFViewer demo         # guided demo (demo_8cores)
#   make -C BTFViewer check-bundle # desktop generated-build freshness (CI)
#   make -C BTFViewer check-web    # web generated-build freshness (CI)
#   make -C BTFViewer check-docs   # links, EN/zh-TW parity, PDF/HTML freshness
#   make -C BTFViewer ci-gate      # tests + generated builds + docs gate
#   make -C BTFViewer ai-test      # offline AI benchmark (tests/ai)
#   make -C BTFViewer ai-test-live # live suite XML → AI_BENCHMARK.md (AI_CONFIG)
#   make -C BTFViewer ai-prompts   # on-demand AI prompt dump → builds/ai_prompts_review.txt

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
MARP ?= npx --yes @marp-team/marp-cli
DOCS := docs

DEMO_XML ?= demos/demo_8cores/demo_8cores.xml
DEMO_LANG ?=
DEMO_LANGS ?= en,zh-tw
DEMO_XTF ?= $(BUILDS)/demo_8cores.xtf
AI_DATASET ?= tests/ai
AI_FAIL_UNDER ?= 70
AI_CONFIG ?= examples/ai/benchmark.xml
AI_MODELS ?=
AI_CASES ?=
AI_CONTEXT ?=
AI_REPLACE ?=

.PHONY: all help web bundle check-bundle check-web check-docs check-builds \
	test test-web test-all ai-test ai-test-live ai-test-context ai-prompts \
	ci ci-gate doc update-images demo demo-voice demo-pack

help:
	@echo "BTF Viewer — make targets"
	@echo ""
	@echo "  make              Build web + desktop (default)"
	@echo "  make web          Web viewer only → builds/btf_viewer.html"
	@echo "  make bundle       Desktop bundle only → builds/btf_viewer.py"
	@echo "  make check-bundle Fail if builds/btf_viewer.py ≠ fresh bundle from sources"
	@echo "  make check-web    Fail if builds/btf_viewer.html ≠ fresh web build (pinned date)"
	@echo "  make check-docs   Links, EN/zh-TW heading parity, PDF/HTML/bundle freshness"
	@echo "  make check-builds check-bundle + check-web"
	@echo "  make doc          Convert README/STATISTICS/AI/WORKFLOWS (+ zh-TW) → docs/*.pdf"
	@echo "  make update-images  Regenerate ../images/stats/*.svg via the desktop CLI"
	@echo "  make demo         Run guided demo via builds/btf_viewer.py (DEMO_XML, DEMO_LANG)"
	@echo "  make demo-voice   Voice pack status (DEMO_XML). See scripts/demo_voice.py"
	@echo "  make demo-pack    Pack demos/demo_8cores → builds/demo_8cores.xtf (DEMO_LANGS=en,zh-tw or all)"
	@echo "  make test         Desktop unit tests (QT_QPA_PLATFORM=offscreen)"
	@echo "  make test-web     Web unit tests (node --test)"
	@echo "  make test-all     Desktop + web unit tests"
	@echo "  make ai-test      Offline AI benchmark ($(AI_DATASET); AI_FAIL_UNDER=$(AI_FAIL_UNDER))"
	@echo "  make ai-test-live Live suite XML → AI_BENCHMARK.md (AI_CONFIG=$(AI_CONFIG); 10× retry, 10s each)"
	@echo "  make ai-test-context Live suite, all three context modes → AI_BENCHMARK.md (10× retry, 10s each)"
	@echo "                      Subset of XML models: AI_MODELS=id1,id2"
	@echo "                      Subset of dataset cases: AI_CASES=id1,id2"
	@echo "                      ai-test-live single context mode: AI_CONTEXT=compact|balanced|full"
	@echo "                      A run restricted this way merges into an existing AI_BENCHMARK.md"
	@echo "                      instead of overwriting it; AI_REPLACE=1 forces a full overwrite"
	@echo "  make ai-prompts   Export AI prompts for review → builds/ai_prompts_review.txt (on demand)"
	@echo "  make ci-gate      test-all + check-builds + check-docs (lightweight CI gate)"
	@echo "  make ci           Alias for ci-gate"
	@echo "  make help         Show this help"
	@echo ""
	@echo "Variables: PYTHON=$(PYTHON)  TRACE=$(TRACE)  PANDOC=$(PANDOC)  MARP=$(MARP)  STATS_TRACE=$(STATS_TRACE)  MIGRATION_TRACE=$(MIGRATION_TRACE)  DEMO_XML=$(DEMO_XML)  DEMO_LANG=$(DEMO_LANG)  DEMO_LANGS=$(DEMO_LANGS)  AI_DATASET=$(AI_DATASET)  AI_FAIL_UNDER=$(AI_FAIL_UNDER)  AI_CONFIG=$(AI_CONFIG)  AI_MODELS=$(AI_MODELS)  AI_CASES=$(AI_CASES)  AI_CONTEXT=$(AI_CONTEXT)  AI_REPLACE=$(AI_REPLACE)"


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
	BTFVIEWER_DEMO_LANG="$(DEMO_LANG)" $(PYTHON) $(OUT) $(DEMO_XML)

demo-voice:
	$(PYTHON) scripts/demo_voice.py status $(DEMO_XML)

demo-pack:
	mkdir -p $(BUILDS)
	@if [ "$(DEMO_LANGS)" = "all" ]; then \
		$(PYTHON) scripts/demo_pack.py demos/demo_8cores -o $(DEMO_XTF) --all-voices; \
	else \
		$(PYTHON) scripts/demo_pack.py demos/demo_8cores -o $(DEMO_XTF) --voice $(DEMO_LANGS); \
	fi

# Demo launches builds/btf_viewer.py; rebuild when package sources change.
BUNDLE_SRCS := $(wildcard btf_viewer_pkg/*.py) \
	$(wildcard btf_viewer_pkg/mvvm/*.py) \
	scripts/bundle_viewer.py
$(OUT): $(BUNDLE_SRCS)
	$(MAKE) bundle

test-web:
	$(MAKE) -C web test

test-all: test test-web

ai-test:
	PYTHONPATH=. QT_QPA_PLATFORM=offscreen $(PYTHON) -m btf_viewer_pkg ai-test \
		--dataset $(AI_DATASET) --fail-under $(AI_FAIL_UNDER) \
		$(if $(AI_CASES),--only-cases $(AI_CASES),)

ai-test-live:
	PYTHONPATH=. QT_QPA_PLATFORM=offscreen $(PYTHON) -m btf_viewer_pkg ai-test \
		--config $(AI_CONFIG) $(if $(AI_MODELS),--models $(AI_MODELS),) \
		$(if $(AI_CASES),--only-cases $(AI_CASES),) \
		$(if $(AI_CONTEXT),--context-mode $(AI_CONTEXT),) \
		$(if $(AI_REPLACE),--replace-report,) \
		--fail-under 0 -o AI_BENCHMARK.md

ai-test-context:
	PYTHONPATH=. QT_QPA_PLATFORM=offscreen $(PYTHON) -m btf_viewer_pkg ai-test \
		--config $(AI_CONFIG) $(if $(AI_MODELS),--models $(AI_MODELS),) \
		$(if $(AI_CASES),--only-cases $(AI_CASES),) \
		$(if $(AI_REPLACE),--replace-report,) \
		--compare-context --fail-under 0 -o AI_BENCHMARK.md

# On-demand AI prompt dump for debugging (not part of all/web/bundle).
ai-prompts:
	mkdir -p $(BUILDS)
	PYTHONPATH=. $(PYTHON) scripts/export_ai_prompts.py -o $(BUILDS)/ai_prompts_review.txt

# Pin About-panel date from the current HTML so a no-op rebuild stays identical.
# Compares a fresh build to the existing artifact (not git HEAD), so a local
# `make web` followed by `make check-web` passes before you commit.
check-web:
	@test -f builds/btf_viewer.html || { echo "error: builds/btf_viewer.html missing — run: make -C BTFViewer web" >&2; exit 1; }
	@DATE="$${BTF_BUILD_DATE:-$$($(PYTHON) scripts/ci_gate.py --print-html-build-date)}"; \
	if [ -z "$$DATE" ]; then DATE=$$(date -u +%F); fi; \
	prev=$$(mktemp $(BUILDS)/btf_viewer.html.prev.XXXXXX); \
	cp builds/btf_viewer.html "$$prev"; \
	echo "check-web: rebuilding with BTF_BUILD_DATE=$$DATE"; \
	if ! BTF_BUILD_DATE="$$DATE" $(MAKE) -C web build; then rm -f "$$prev"; exit 1; fi; \
	if ! cmp -s "$$prev" builds/btf_viewer.html; then \
	  rm -f "$$prev"; \
	  echo "error: builds/btf_viewer.html was stale relative to web sources." >&2; \
	  echo "It has been regenerated — re-run: make -C BTFViewer check-web" >&2; \
	  exit 1; \
	fi; \
	rm -f "$$prev"; \
	echo "OK: builds/btf_viewer.html matches web sources"

check-docs:
	$(PYTHON) scripts/ci_gate.py --all

check-builds: check-bundle check-web

ci-gate: test-all check-builds check-docs

ci: ci-gate

DOC_PDFS := \
	$(DOCS)/README.pdf $(DOCS)/STATISTICS.pdf $(DOCS)/AI.pdf $(DOCS)/WORKFLOWS.pdf \
	$(DOCS)/README_zh-TW.pdf $(DOCS)/STATISTICS_zh-TW.pdf \
	$(DOCS)/AI_zh-TW.pdf $(DOCS)/WORKFLOWS_zh-TW.pdf

doc: $(DOC_PDFS)

# Use the vendored Eisvogel template (scripts/eisvogel.latex). Do not pass
# `--template=eisvogel`: pandoc prefers ~/.local/share/pandoc/templates/eisvogel.latex,
# and a 0-byte file there yields an empty .tex and xelatex "no legal \end found".
#
# `-f markdown-blank_before_header`: README.md/AI.md put a `<a id=... name=...>`
# anchor directly above every heading (no blank line, for stable GitHub anchors).
# Pandoc's default +blank_before_header extension then refuses to parse those
# `#`/`##` lines as headings at all — they show up as literal "# Heading" body
# text in the PDF. Disabling the extension restores normal heading rendering.
#
# Mermaid: ```mermaid fences are rendered to PNG via scripts/mermaid-filter.lua
# (mmdc or npx @mermaid-js/mermaid-cli). Cached under builds/mermaid-cache/.
#
# GitHub `<a id="…">` anchors: scripts/html-anchor-filter.lua emits LaTeX
# \hypertarget so in-document links match GitHub slugs (Keyboard & mouse, etc.).
#
# Sibling manuals: scripts/md-pdf-links.lua turns STATISTICS.md#… into
# STATISTICS.pdf#… (and *_zh-TW.md → *_zh-TW.pdf) so PDF cross-links land
# on those hypertargets.
#
# Emoji: DejaVu has no ❌/🟢/🟡/🔴; scripts/emoji-fallback.lua substitutes
# for LaTeX only (GitHub keeps the UI glyphs).
#
# Tables: scripts/table-widths.lua sizes columns from cell text so a short
# `| --- |` ruler cannot squeeze the first column until names overprint.
#
# CJK: DejaVu has no 中/文. If xeCJK.sty is installed, Eisvogel uses it
# (override font with CJK_MAINFONT=…). Otherwise fontspec + ucharclasses
# (scripts/cjk-fallback.tex) — this machine often has Droid Sans Fallback
# without texlive-xecjk. Required for *_zh-TW.md PDFs.
CJK_MAINFONT ?= $(shell fc-list :lang=zh family 2>/dev/null | head -1 | cut -d',' -f1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$$//')
HAS_XECJK := $(shell kpsewhich xeCJK.sty 2>/dev/null)
CJK_HEADER := $(if $(and $(CJK_MAINFONT),$(if $(HAS_XECJK),,1)),$(BUILDS)/cjk-fallback.tex,)
PANDOC_PDF_FLAGS := --pdf-engine=xelatex \
    --template=scripts/eisvogel.latex \
	--lua-filter scripts/math-codeblock.lua \
	--lua-filter scripts/mermaid-filter.lua \
	--lua-filter scripts/html-anchor-filter.lua \
	--lua-filter scripts/md-pdf-links.lua \
	--lua-filter scripts/emoji-fallback.lua \
	--lua-filter scripts/table-widths.lua \
	--lua-filter scripts/cjk-image-alt.lua \
	--include-in-header=scripts/table-layout.tex \
	--include-in-header=scripts/figure-maxsize.tex \
	--resource-path=..:. \
	-f markdown-blank_before_header \
	-V mainfont="DejaVu Sans" \
	-V monofont="DejaVu Sans Mono" \
	$(if $(and $(CJK_MAINFONT),$(HAS_XECJK)),-V CJKmainfont="$(CJK_MAINFONT)" -V CJKmonofont="$(CJK_MAINFONT)",) \
	$(if $(CJK_HEADER),--include-in-header=$(CJK_HEADER),) \
	-V colorlinks=true

DOC_LUA := scripts/mermaid-filter.lua scripts/math-codeblock.lua \
	scripts/html-anchor-filter.lua scripts/md-pdf-links.lua \
	scripts/emoji-fallback.lua scripts/table-widths.lua \
	scripts/cjk-image-alt.lua
DOC_TEX := scripts/table-layout.tex scripts/figure-maxsize.tex

# Noto Sans CJK TC for Traditional Chinese manuals (Latin + CJK in one face).
CJK_FONT_DIR := scripts/fonts
CJK_FONT_REG := $(CJK_FONT_DIR)/NotoSansCJKtc-Regular.otf
CJK_FONT_BOLD := $(CJK_FONT_DIR)/NotoSansCJKtc-Bold.otf
CJK_FONT_URL_BASE := https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese
PANDOC_PDF_FLAGS_ZHTW := --pdf-engine=xelatex \
    --template=scripts/eisvogel.latex \
	--lua-filter scripts/math-codeblock.lua \
	--lua-filter scripts/mermaid-filter.lua \
	--lua-filter scripts/html-anchor-filter.lua \
	--lua-filter scripts/md-pdf-links.lua \
	--lua-filter scripts/emoji-fallback.lua \
	--lua-filter scripts/table-widths.lua \
	--lua-filter scripts/cjk-image-alt.lua \
	--include-in-header=scripts/table-layout.tex \
	--include-in-header=scripts/cjk-zh-tw.tex \
	--include-in-header=scripts/figure-maxsize.tex \
	--resource-path=..:. \
	-f markdown-blank_before_header \
	-V mainfont="NotoSansCJKtc-Regular.otf" \
	-V mainfontoptions="Path=$(CJK_FONT_DIR)/,BoldFont=NotoSansCJKtc-Bold.otf,ItalicFont=NotoSansCJKtc-Regular.otf,BoldItalicFont=NotoSansCJKtc-Bold.otf" \
	-V sansfont="NotoSansCJKtc-Regular.otf" \
	-V sansfontoptions="Path=$(CJK_FONT_DIR)/,BoldFont=NotoSansCJKtc-Bold.otf,ItalicFont=NotoSansCJKtc-Regular.otf,BoldItalicFont=NotoSansCJKtc-Bold.otf" \
	-V monofont="NotoSansCJKtc-Regular.otf" \
	-V monofontoptions="Path=$(CJK_FONT_DIR)/,BoldFont=NotoSansCJKtc-Bold.otf,ItalicFont=NotoSansCJKtc-Regular.otf,BoldItalicFont=NotoSansCJKtc-Bold.otf" \
	-V geometry:margin=2.5cm \
	-V colorlinks=true

# Ensure mermaid PNG cache exists before pandoc runs.
$(DOC_PDFS): | $(DOCS)/.mermaid-cache-stamp

$(DOCS)/.mermaid-cache-stamp:
	mkdir -p $(BUILDS)/mermaid-cache
	@touch $@

$(BUILDS)/cjk-fallback.tex: scripts/cjk-fallback.tex
	mkdir -p $(BUILDS)
	sed 's/CJKFONT/$(CJK_MAINFONT)/g' $< > $@

$(CJK_FONT_REG):
	mkdir -p $(CJK_FONT_DIR)
	curl -L --fail -o $@ $(CJK_FONT_URL_BASE)/NotoSansCJKtc-Regular.otf

$(CJK_FONT_BOLD):
	mkdir -p $(CJK_FONT_DIR)
	curl -L --fail -o $@ $(CJK_FONT_URL_BASE)/NotoSansCJKtc-Bold.otf

$(DOCS)/README.pdf: README.md $(DOC_LUA) $(DOC_TEX) $(CJK_HEADER)
	mkdir -p $(DOCS)
	$(PANDOC) $(PANDOC_PDF_FLAGS) -M title="BTF Trace Viewer" $< -o $@

$(DOCS)/STATISTICS.pdf: STATISTICS.md $(DOC_LUA) $(DOC_TEX) $(CJK_HEADER)
	mkdir -p $(DOCS)
	$(PANDOC) $(PANDOC_PDF_FLAGS) -M title="BTF Viewer — Statistics" $< -o $@

$(DOCS)/AI.pdf: AI.md $(DOC_LUA) $(DOC_TEX) $(CJK_HEADER)
	mkdir -p $(DOCS)
	$(PANDOC) $(PANDOC_PDF_FLAGS) -M title="BTF AI Assistant" $< -o $@

$(DOCS)/WORKFLOWS.pdf: WORKFLOWS.md $(DOC_LUA) $(DOC_TEX) $(CJK_HEADER)
	mkdir -p $(DOCS)
	$(PANDOC) $(PANDOC_PDF_FLAGS) -M title="BTF Viewer — Analysis Workflows" $< -o $@

$(DOCS)/README_zh-TW.pdf: README_zh-TW.md $(DOC_LUA) $(DOC_TEX) scripts/cjk-zh-tw.tex $(CJK_FONT_REG) $(CJK_FONT_BOLD)
	mkdir -p $(DOCS)
	$(PANDOC) $(PANDOC_PDF_FLAGS_ZHTW) -M title="BTF Trace Viewer（繁體中文）" $< -o $@

$(DOCS)/STATISTICS_zh-TW.pdf: STATISTICS_zh-TW.md $(DOC_LUA) $(DOC_TEX) scripts/cjk-zh-tw.tex $(CJK_FONT_REG) $(CJK_FONT_BOLD)
	mkdir -p $(DOCS)
	$(PANDOC) $(PANDOC_PDF_FLAGS_ZHTW) -M title="BTF Viewer — Statistics（繁體中文）" $< -o $@

$(DOCS)/AI_zh-TW.pdf: AI_zh-TW.md $(DOC_LUA) $(DOC_TEX) scripts/cjk-zh-tw.tex $(CJK_FONT_REG) $(CJK_FONT_BOLD)
	mkdir -p $(DOCS)
	$(PANDOC) $(PANDOC_PDF_FLAGS_ZHTW) -M title="BTF AI Assistant（繁體中文）" $< -o $@

$(DOCS)/WORKFLOWS_zh-TW.pdf: WORKFLOWS_zh-TW.md $(DOC_LUA) $(DOC_TEX) scripts/cjk-zh-tw.tex $(CJK_FONT_REG) $(CJK_FONT_BOLD)
	mkdir -p $(DOCS)
	$(PANDOC) $(PANDOC_PDF_FLAGS_ZHTW) -M title="BTF Viewer — Analysis Workflows（繁體中文）" $< -o $@

# Fail if builds/btf_viewer.py drifts from package sources (CI / pre-commit).
# Compares a fresh bundle to the existing artifact (not git HEAD), so a local
# `make bundle` followed by `make check-bundle` passes before you commit.
check-bundle:
	mkdir -p $(BUILDS)
	@test -f $(OUT) || { echo "error: $(OUT) missing — run: make -C BTFViewer bundle" >&2; exit 1; }
	@tmp=$$(mktemp $(BUILDS)/btf_viewer.py.check.XXXXXX); \
	$(PYTHON) scripts/bundle_viewer.py -o "$$tmp"; \
	$(PYTHON) -m py_compile "$$tmp"; \
	if ! cmp -s "$$tmp" $(OUT); then \
	  echo "error: $(OUT) is out of date with package sources." >&2; \
	  echo "Run: make -C BTFViewer bundle" >&2; \
	  rm -f "$$tmp"; exit 1; \
	fi; \
	rm -f "$$tmp"; \
	echo "OK: $(OUT) matches package sources"

# Regenerate the statistics distribution plots + task-priority timeline crop
# used as illustrations in README.md / WORKFLOWS.md, headlessly via the desktop
# CLI `snapshot` command (Statistics -> click row equivalents), sourced from
# STATS_TRACE (default: example-8cores.btf).
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
		-o $(STATS_IMG_DIR)/stats-response-cs11.svg --view plot --metric response --task "CS[11]"
	PYTHONPATH=. QT_QPA_PLATFORM=offscreen $(PYTHON) scripts/export_stats_tables.py \
		$(STATS_TRACE) $(STATS_IMG_DIR)
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

