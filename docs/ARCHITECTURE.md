# Architecture

Mojo OCR keeps numerical kernels separate from document plumbing and presentation.

```text
CLI / local browser
       │
       ▼
Pillow / PDFium decoding
       │
       ▼
Threshold / deskew → line projections → connected components / candidate cuts
       │
       ▼
24 × 32 normalized glyph features (768 float32 values)
       │
       ▼
Python-owned buffers → ctypes → Mojo MLP: 768 → 128 ReLU → 94 softmax
       │
       ▼
Geometric spaces / lines → text, JSON, PDF, corrections, SQLite
```

## Source map

| File | Responsibility |
|---|---|
| `kernels.mojo` | SIMD forward pass, stable softmax, cross-entropy, manual backpropagation, momentum SGD |
| `native.py` | Fixed model dimensions, buffer validation/ownership, initialization, checkpoint serialization |
| `imaging.py` | Pixel bounds, preprocessing, normalization, initial segmentation |
| `engine.py` | Model-backed segmentation/recognition, page iteration, overlays, edit distance |
| `training.py` | Seeded local-font synthesis, synthetic replay, training/evaluation loop |
| `app.py` / `ocr` | CLI entry point, exports, glyph review, archive/search, benchmark commands |
| `ui.py` | Loopback HTTP server, bounded uploads, temporary result lifecycle |
| `ui.html`, `ui.css`, `ui.js` | No-build browser UI; text edits remain in the tab until export |
| `tests/` | Independent numerical reference, application tests, HTTP tests, historical validation records |
| `models/` | Audited synthetic baseline checkpoint and training report |

## Native boundary

The C ABI is private and uses raw host addresses. NumPy owns contiguous float32/int64 arrays; `native.py` validates shapes and values before calling Mojo. Do not call the exports with arbitrary buffers or concurrently mutate a model during inference.

Architecture constants must match on both sides. A dimensional change requires a checkpoint-version change and retraining. `.npz` loading disables pickle. A compiled `.so` is not portable across arbitrary CPUs/platforms and is never committed.

## Training contract

The recognizer classifies segmented glyphs, not sequences. Training uses seeded synthetic examples rendered from local fonts. Exported corrections contain exactly the classifier features and one character label. Incorrect segmentation cannot be repaired by labeling a multi-letter crop as a character. Resume is fine-tuning: optimizer state and learning-rate schedule restart.

The benchmark corpus is used in development. Preserve its provenance and distinguish it from independently sampled evaluation data.

## Local UI contract

The UI accepts one file per request and serializes recognition. It stores derivatives in a temporary workspace, uses opaque result IDs, and exposes only allowlisted asset paths. Host/origin checks plus a process token protect mutations against cross-origin browser requests; they are not multi-user authentication.

Browser text edits intentionally do not mutate the original OCR JSON, PDFs, or model. Clear affects all tabs using that server. Input and output data are unencrypted. See [security policy](../SECURITY.md) and [usage](USAGE.md) for resource/lifecycle limitations.

## Scope boundaries

No web framework, frontend bundler, model service, cloud account, OCR engine fallback, or native accelerator SDK is needed. Prefer measured improvements to these small components over speculative abstractions. A future line recognizer should be a clearly evaluated architectural change, not disguised as a minor glyph-model tweak.
