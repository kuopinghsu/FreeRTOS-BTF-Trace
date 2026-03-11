NPM     ?= npm
OUTDIR  := dist
OUT     := $(OUTDIR)/index.html

.PHONY: all build dev preview dist-clean

all: build

## Install dependencies and produce dist/index.html (single self-contained file)
build: node_modules
	$(NPM) run build

## Start Vite development server with HMR
dev: node_modules
	$(NPM) run dev

## Preview the production build locally
preview: $(OUT)
	$(NPM) run preview

## Install npm dependencies (runs only when package.json changes)
node_modules: package.json
	$(NPM) install
	@touch node_modules

## Remove build output and installed dependencies
dist-clean: clean
	-rm -rf node_modules package-lock.json
