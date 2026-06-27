NPM     ?= npm
BUILDS  := ../builds
RELEASE := $(BUILDS)/btf_viewer.html

.PHONY: all build dev preview clean dist-clean test

all: build

## Install dependencies and produce builds/btf_viewer.html (single self-contained file)
build: node_modules wasm
	$(NPM) run build
	rm -rf dist

## Compile WASM timeline accelerator and embed base64 for single-file build
wasm:
	node scripts/embed-wasm.mjs

## Start Vite development server with HMR
dev: node_modules
	$(NPM) run dev

## Serve builds/btf_viewer.html over HTTP (recommended for large traces)
preview: $(RELEASE)
	@echo "→ http://localhost:4173/btf_viewer.html"
	cd $(BUILDS) && python3 -m http.server 4173

## Install npm dependencies (runs only when package.json changes)
node_modules: package.json
	$(NPM) install
	@touch node_modules

## Remove build output
clean:
	rm -rf dist
	rm -f $(RELEASE)

## Remove build output and installed dependencies
dist-clean: clean
	-rm -rf node_modules package-lock.json

## Overlay draw smoke tests (node --test)
test: node_modules
	$(NPM) test
