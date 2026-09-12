# Mojo OCR usage guide

[← Project overview](../README.md)

An **offline, from-scratch printed-text OCR toolkit**. Includes a trained ~403 KiB model—not a wrapper around Tesseract, an OCR API, or pretrained neural weights.

After following the [installation instructions](../README.md#start-here), run these commands from your clone's root:

```bash
cd mojo-ocr
./ocr read examples/note.png
./ocr read examples/code.png
```

Output from the included note:

```text
Save this note
Budget: $42.75
Room 204
```

## Browser UI

```bash
# From the repository root:
./ocr serve
# Open http://localhost:8878
```

A simple local workspace with:

- Drag-and-drop/file-picker upload or clipboard image paste.
- A **Try an example** button to get started without using personal files.
- Text/numbers or numbers-only recognition, rotation, deskew, and lighting controls.
- Page previews, optional confidence boxes, and editable extracted text.
- Copy the current page; download all edited pages as text, or the original OCR JSON/searchable PDF.

The UI processes one file at a time, up to **25 MiB and 20 pages**. PDF resolution is selectable (150/200/300 DPI), subject to the existing 24-million-pixel page limit. **Text edits are only for text export: they do not retrain the model or update the PDF/JSON.** Use the separate glyph-review/retraining workflow below to personalize recognition.

`./ocr serve --port 8879 --model models/personal.npz` selects another port/model. No extra packages or cloud services are required. The server binds **only to 127.0.0.1**, including when used from a Windows browser with WSL localhost forwarding. It is a single-user tool, not an authenticated multi-user service; do not expose it through a public proxy or tunnel.

Uploaded originals are removed after successful processing. Temporary derivatives are stored in an OS temporary directory: **Clear** deletes all server results (including other tabs), and a normal Ctrl+C shutdown deletes the workspace. Up to ten recent result sets are retained; links expire after one hour and old sets are pruned on subsequent uploads. An abrupt kill/crash may leave temporary files behind. Text edits live only in the browser tab until downloaded. Downloads are not deleted by Clear. All these artifacts are unencrypted.

The interface sources are `ui.py`, `ui.html`, `ui.css`, and `ui.js`; HTTP upload/export/security tests are in `tests/test_ui.py`.

## What it is good for

- Clean screenshots, terminal/code captures, and straight, high-contrast printed text.
- Extracting text from PNG/JPEG/WebP/BMP/TIFF and PDFs, including multipage files.
- A private searchable archive of documents and screenshots using SQLite FTS5.
- Creating **new searchable raster PDFs** with an invisible text layer.
- Reviewing uncertain glyphs, collecting corrections, and training your own model locally.
- Experimenting with real Mojo SIMD inference, backpropagation, and optimization.

**Experimental, not a general-purpose commercial OCR replacement.** The model supports the 94 non-space printable ASCII characters; spaces/newlines are reconstructed geometrically. No handwriting, Unicode, language model, automatic translation, robust table/column reconstruction, or scene-text detector. Small/blurry/italic text, ligatures, unfamiliar fonts, photographs, mixed sizes on one line, and complex layouts can fail. Verify money, identifiers, URLs, and other important text even when confidence is high.

## Install / rebuild

```bash
./setup.sh
```

Requires `mojo` **1.0.0**, `uv`, and local TrueType/OpenType fonts for training. Tested on CPython 3.13.4, aarch64 Linux, an 8-core Qualcomm CPU, and ~8 GiB RAM. Setup installs pinned Python dependencies into `.venv` and compiles `libocr.so`. It does **not** retrain or download weights.

Initial dependency installation needs a package connection. Thereafter, extraction, training from installed fonts, review, and search are local and require no network. The toolkit has no cloud-upload or telemetry code; browser uploads go only to the local UI server. The installed compiler may print a harmless missing-Crashpad-handler warning during compilation.

The `.so` is machine-specific: rebuild on another machine. The `.npz` checkpoint is portable between compatible builds. GPU/NPU execution is **not implemented**. This repository contains only the standalone OCR project.

## Everyday commands

### Image / screenshot → text

```bash
./ocr read ~/Pictures/screenshot.png
./ocr read ~/Pictures/screenshot.png --json > screenshot.json
```

Use your desktop screenshot tool to save a screen or region, then pass that file. This project does not silently capture your screen or watch personal folders. In WSL, Windows files are accessible through paths such as `/mnt/c/Users/<WindowsUser>/Pictures/`; quote paths containing spaces. Run `explorer.exe .` from an output directory to open its review HTML in your Windows browser.

### PDF / folder → text, JSON, searchable PDF

```bash
./ocr read ~/Documents/scan.pdf --out ./output/scans --pdf --overlay --review
./ocr read ~/Pictures/receipts --recursive --out ./output/receipts
./ocr read scan.pdf --dpi 200 --max-pages 300 --out ./output/scans
```

With `--out`, every source produces `.txt` and `.json`; optional outputs are `.searchable.pdf`, per-page `.overlay.png`, and per-page `.review.html`. Filenames include a short hash of the absolute source path to avoid collisions between equal basenames. Re-running overwrites the corresponding **generated outputs**, never the source. Keep output folders outside recursively scanned input folders to avoid re-ingesting results.

JSON includes text, line/character boxes, top-three alternatives, raw softmax confidence, uncertain flags, timing, and model SHA-256. Red boxes in overlays mean low model confidence, **not a reliable error detector**. Scores are not calibrated and can be confidently wrong. Nothing is silently spell-corrected.

Searchable PDFs are new, rasterized documents. They **do not preserve** original vector content, forms, annotations, signatures, metadata, or original embedded text. The invisible text's positioning is approximate. Do not replace archival originals with these derivatives.

### Difficult input / numeric regions

```bash
# Coordinates are source image pixels; for PDFs, rendered pixels at --dpi.
./ocr read receipt.png --crop 100 200 500 150 --whitelist '0123456789.,-$'

# Explicit right-angle orientation; optional small-angle deskew.
./ocr read sideways.png --rotate 270 --deskew

# Uneven lighting or manual threshold (0..255).
./ocr read scan.jpg --adaptive --deskew
./ocr read scan.jpg --threshold 150

# Raise this to insert fewer spaces; lower to insert more.
./ocr read screenshot.png --space-factor 1.15
```

Dark backgrounds are automatically inverted for recognition. Alpha is composited on white; EXIF orientation is respected. Deskew searches only **±3°**, not arbitrary orientation. Adaptive normalization is a basic background filter, not robust photographic-document processing.

Boxes refer to the **cropped, rotated, deskewed output image**, not untouched source coordinates. Crop runs before EXIF normalization/rotation. PDF default is 150 DPI, maximum 100 pages per file unless explicitly raised, and maximum 24 million pixels per processed page. Reduce PDF DPI or crop/downsample oversized images with an image editor before passing them to the CLI.

Monospaced lines use a detected character pitch to reconstruct spaces and indentation. Proportional text uses gap heuristics; exact indentation and whitespace are not guaranteed. Multi-column pages are read across rows rather than separated into reading-order blocks—crop columns separately.

### Private search archive

```bash
./ocr index ~/Documents/scans ~/Pictures/screenshots --recursive --db ./output/personal.sqlite3
./ocr search 'invoice' --db ./output/personal.sqlite3
./ocr search '"invoice" OR "receipt"' --fts --db ./output/personal.sqlite3
```

Results show source path, page, and a snippet. The default search is a literal phrase; `--fts` enables SQLite FTS5 syntax. Reindexing replaces each successfully processed file's old pages without duplicates. Failed OCR leaves that file's previous index intact and exits nonzero. Deleted source files are not automatically pruned; rebuild the database to remove obsolete entries. Reindex after changing the model or preprocessing settings.

**Privacy:** generated text, review pages, PDFs, correction files, and SQLite indexes contain readable copies of document content and are **not encrypted**. Use your normal disk encryption/access controls. Review HTML embeds the page image; don't share it accidentally.

## Train and personalize

### Reproduce the included scratch training

```bash
./ocr train --samples 600 --epochs 32 --seed 42 --model models/my-print.npz
./ocr read examples/note.png --model models/my-print.npz
```

This creates **56,400** balanced training glyphs using eight installed fonts, plus 7,050 independently seeded same-font validation glyphs. Images vary font size, line context, binarization, mild blur, and vertical bounds. No fonts, datasets, or weights are fetched. The best validation-cross-entropy checkpoint is saved atomically with metadata; a `.training.json` report records the run. Reproducibility assumes the same font files, dependencies, compiler, and hardware.

### Match your own fonts

```bash
./ocr train \
  --font /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf \
  --font /path/to/your-font.ttf \
  --samples 800 --epochs 32 --model models/personal.npz
```

Supplying `--font` replaces the default font list. Use fonts you are entitled to use. Font files themselves are not bundled or redistributed. Specializing to the actual fonts in your screenshots is usually more useful than just training longer. This glyph architecture still cannot learn robust page layout through font training.

### Correct mistakes and fine-tune

```bash
./ocr read screenshot.png --out ./output/review --review --overlay
# Open the generated .review.html locally in a browser.
# Change incorrect one-character labels and download corrections.json.
./ocr train --resume models/print-v1.npz \
  --corrections ~/Downloads/corrections.json \
  --epochs 8 --lr 0.0005 --model models/personal.npz
```

Review pages work without a server or internet and export **changed glyph labels only**. The normalizer features are embedded so overlapping-component crops are trained exactly as recognized. Every label must be one supported character. Multiple corrections files are accepted.

**Do not label a crop that contains multiple letters, an incomplete letter, or background noise as one character.** Those are segmentation problems and this correction format cannot repair them. Fine-tuning oversamples corrected glyphs alongside synthetic replay to reduce forgetting. `--resume` loads weights but resets optimizer momentum and the learning-rate schedule: it is fine-tuning, not exact interrupted-run continuation. Best-checkpoint selection remains based on synthetic validation, not an independent test of your corrections. Save to a new model and evaluate real examples before adopting it.

## Measure quality on your documents

Create `evaluation.json` next to your examples:

```json
[
  {"image": "scan.png", "text": "scan-truth.txt"},
  {"image": "screenshot.png", "text": "screenshot-truth.txt"}
]
```

```bash
./ocr evaluate evaluation.json --model models/personal.npz > evaluation-results.json
./ocr benchmark --model models/personal.npz --out ./output/benchmark-personal
.venv/bin/python -m unittest discover -s tests -v
```

Paths in an evaluation manifest are relative to the manifest. Ground-truth text must be UTF-8; trailing newlines are stripped. For multipage documents, pages are joined with `\n\f\n`. CER is `(substitutions + insertions + deletions) / reference characters`; whitespace and case count. Synthetic benchmark WER splits on whitespace and reports word-level edit rate. Neither metric should be called overall “accuracy” without qualification.

### Current measured baseline on this machine

| Measurement | Result |
|---|---:|
| Parameters | 110,558 |
| Compressed checkpoint | 412,231 bytes (~403 KiB) |
| Same-font synthetic glyph validation | 99.15% accuracy |
| Unseen-font synthetic glyph evaluation | 89.04% accuracy |
| Synthetic document CER, all renderings | **2.96%** |
| Document CER, training fonts | 1.66% |
| Document CER, unseen fonts | 6.21% |
| Synthetic document WER, all renderings | 12.43% |
| Median warm page processing, 900×230 | ~39 ms |
| 32-epoch training/validation loop | ~74 s, excluding data generation |

The document corpus is **84 renderings of four passages**, across seven fonts and clean/blurred/dark variants—not 84 independent real documents. It was used while developing segmentation, so it is a **development/regression benchmark**, not a blind estimate of real-world performance. Unseen fonts were excluded from weight training but their evaluation results were inspected. No user documents were accessed for testing. CLI startup, model loading, PDF rendering, and export are excluded from the per-page timing.

Full predictions, ground truth, timings, and model fingerprint: [`benchmarks/report.json`](../benchmarks/report.json). Training details: [`models/print-v1.training.json`](../models/print-v1.training.json). See [`MODEL_CARD.md`](../MODEL_CARD.md).

## Architecture / hacking

```text
Image/PDF
  → Pillow/PDFium decode
  → threshold + optional background correction/deskew
  → row projections, connected components, candidate cuts
  → 24×32 glyph/line-context features
  → Mojo: 768 → 128 ReLU → 94 softmax
  → geometric spaces / lines
  → text, JSON, review, PDF, SQLite
```

- **`kernels.mojo`**: actual neural computation. Float32 SIMD dot products, stable softmax, cross-entropy, manual backpropagation, and momentum SGD with L2 decay. No ML framework or automatic differentiation.
- **`native.py`**: small `ctypes` bridge, validated NumPy buffers, seeded He initialization, non-pickle checkpoints. Python owns the memory; Mojo does the neural arithmetic.
- **`training.py`**: synthetic font renderer and training/evaluation loop.
- **`imaging.py`, `engine.py`**: preprocessing, inspectable segmentation, model-guided splitting, recognition, PDF page iteration.
- **`app.py`**: CLI, local review export, archive, searchable PDF, benchmarks.
- **`tests/test_ocr.py`**: ten tests, including Mojo forward/backprop/optimizer agreement with an independent NumPy reference and end-to-end PDF/index/correction checks.

Reusable Python API (run from this directory or add it to `sys.path`):

```python
from PIL import Image
from engine import OCR
ocr = OCR("models/print-v1.npz")  # Load once, reuse for many pages.
result, normalized_image, binary_mask = ocr.image(Image.open("example.png"))
print(result["text"])
```

The private C ABI takes raw host addresses and fixed architecture constants. Use `Model` rather than calling exports directly. Do not concurrently train and infer on the same model instance. Changing the architecture requires synchronized Mojo/Python constants, a new checkpoint version, rebuilding, and retraining.

### Best next improvements

1. Collect a genuinely representative, manually labeled test set from your use cases.
2. Add font coverage / corrected glyphs based on those errors.
3. For handwriting, dense ligatures, or arbitrary photographs, replace the segmented-glyph recognizer with a line-level CNN/recurrent or transformer model trained with CTC and a text detector. That is a larger training/data project—not something this small MLP can acquire merely by adding epochs.
4. Only then investigate NPU export/inference against the supported Qualcomm toolchain. This project makes no NPU acceleration claim.
