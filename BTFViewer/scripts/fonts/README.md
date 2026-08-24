# CJK fonts for `make doc` (zh-TW PDFs)

`make doc` downloads Noto Sans CJK TC here when building
`docs/*_zh-TW.pdf`. Files are gitignored (~32 MB).

| File | Source |
|------|--------|
| `NotoSansCJKtc-Regular.otf` | [googlefonts/noto-cjk](https://github.com/googlefonts/noto-cjk) Sans/OTF/TraditionalChinese |
| `NotoSansCJKtc-Bold.otf` | same |

English PDFs keep DejaVu + optional system CJK fallback (`scripts/cjk-fallback.tex`).
