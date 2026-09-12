# Model card: print-v1

## Identity and intended use

- **File:** `models/print-v1.npz`
- **SHA-256:** `a092f06597aadd0ed5d487e33bcccb99ac971877cfefd225386a198d2806a808`
- **Architecture:** 768 input features → 128 ReLU units → 94-way softmax.
- **Parameters:** 110,558 float32 values; compressed file 412,231 bytes.
- **Alphabet:** ASCII codepoints 33–126. Whitespace is outside the classifier.
- **Execution:** Mojo 1.0.0 native ARM CPU kernels. No NPU/GPU path.
- **Purpose:** personal experiments and clean printed-text/screenshot extraction; a starting point for local specialization.

This is a real neural classifier trained from seeded random He-initialized weights. There is no pretrained OCR model, transformer, external inference API, dictionary, or language-model correction hidden in the pipeline. Python handles data generation, preprocessing, buffer ownership, and application I/O. Neural forward propagation, softmax, loss, backpropagation, and momentum SGD are implemented in Mojo.

## Training provenance

- Seed 42; 56,400 balanced synthetic glyphs (600/class).
- Eight locally installed fonts: DejaVu Sans regular/bold, DejaVu Sans Mono regular/bold, DejaVu Serif regular, Liberation Sans/Mono/Serif regular.
- Font sizes 17–48 pixels; multiple line-height contexts, varied threshold, mild blur, and line-bound padding.
- Separately seeded validation: 7,050 glyphs from the same fonts.
- 32 epochs; sample-wise momentum SGD, momentum 0.8, initial LR 0.003 decreasing linearly to 0.00045, L2 coefficient 0.00001 on weights only.
- Best validation-cross-entropy checkpoint: epoch 31.
- Training/validation loop: approximately 74 seconds on this machine, excluding synthetic generation and final unseen-font evaluation.
- No user documents, private data, downloaded datasets, or pretrained weights used.

Font files are not redistributed. The examples are synthetic raster images. Dependencies and fonts remain subject to their own licenses.

The original training and recorded benchmark used Pillow 12.1.1. The public runtime now pins **Pillow 12.3.0** to address known upstream security advisories. The baseline weights were not regenerated. A publication-time rerun with the patched dependency produced identical text predictions on all 84 benchmark renderings and passed all 13 application/numerical/HTTP tests; see `tests/publication-validation.json`. The original timing report remains historical, not a promise about the current runtime.

## Evaluation

| Evaluation | Result |
|---|---:|
| Same-font glyph validation accuracy | 99.15% |
| Unseen-font glyph accuracy, 2,820 glyphs | 89.04% |
| Document character error rate, all | 2.96% |
| Document character error rate, training fonts | 1.66% |
| Document character error rate, unseen fonts | 6.21% |
| Document word error rate, all | 12.43% |

Unseen fonts are FreeSans and FreeMono. The document benchmark comprises **four fixed passages**, seven font choices, and three render variants (clean, 0.6-pixel Gaussian blur, inverted dark background): 84 renderings total. It contains short notes, receipt-like text, contact details, and code. Source images are 900×230 pixels with 30-pixel fonts.

**The segmentation code was developed against this document corpus. It is not a blind test set.** Unseen fonts are unseen by weight training, not uninspected by the developer. These results must not be generalized to real scans, arbitrary fonts, photos, handwriting, or languages. Renderings sharing a passage/font are correlated. Glyph validation also measures a much easier task than full OCR.

The ~39 ms/page median measures warm in-process preprocessing, segmentation, and recognition—not CLI startup, model loading, PDF rasterization, output generation, or large-page performance. Ten automated tests check numerical correctness and application workflows; they do not establish production-level recognition quality.

Reports:
- `models/print-v1.training.json`: training history and glyph confusion counts.
- `benchmarks/report.json`: every document prediction, reference, error count, timing, and checkpoint hash.
- `tests/validation.json`: local test execution evidence.

## Important failure modes

- Visually ambiguous `I/l/|`, `O/0`, `1/l`, case variants, and punctuation.
- `fi`/`fl` ligatures and genuinely connected character sequences; candidate vertical cuts are heuristic.
- Segmentation merges/splits, disconnected quotation marks, noise mistaken for text, or text omitted entirely.
- Short/atypical lines where baseline/line bounds differ from synthetic training contexts.
- Unfamiliar fonts, italics, tiny text, compression artifacts, strong blur, skew beyond ±3°, perspective, and uneven backgrounds.
- Multi-column order, exact proportional-font whitespace, tables, forms, and mixed-size text.
- Non-ASCII text and handwriting are outside scope. Such input can still produce confident ASCII nonsense.

Softmax confidence is **uncalibrated** and not an estimate that an entire word/page is correct. Whitelisting restricts output but does not increase reliability or renormalize the exposed confidence. Important financial/legal/medical text must be reviewed against the source. This model should not be used as an unattended decision-making system.

## Personalization and privacy

Local review exports changed one-character labels with the exact normalized classifier input. Fine-tuning replays synthetic glyphs and resets optimizer state. Corrections do not train segmentation, reading order, or a sequence recognizer. Evaluate an independently labeled personal test set before replacing the default model.

No OCR/training data is uploaded by this project. Images, text, HTML review pages, correction datasets, PDFs, and SQLite archives are unencrypted local artifacts. Protect them as you would their source documents. The Python dependencies are fetched only during installation; inference does not fetch models or contact a service.
