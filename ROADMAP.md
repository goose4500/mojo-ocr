# Mojo OCR roadmap

This is a direction, not a delivery-date commitment. Open an issue to discuss priorities or propose a scoped implementation.

## Foundation — available

- [x] From-scratch 94-class printed-ASCII model with Mojo training/inference.
- [x] Image/PDF extraction, text/JSON output, searchable raster PDFs.
- [x] Local browser workspace with previews and editable text.
- [x] Glyph correction export, custom-font training, and local search.
- [x] Numerical tests, synthetic benchmark, and transparent model card.
- [x] Standalone public repository, MIT license, and cross-architecture CI.

## Next: make daily use more reliable

- [ ] Collect an independently labeled, redistributable real-document evaluation set.
- [ ] Improve connected/ligature segmentation and proportional-font whitespace.
- [ ] Add a UI region-crop tool and clearer uncertain-glyph inspection.
- [ ] Add browser batch queues and intentional cancellation/resource cleanup.
- [ ] Make evaluation/model comparison and personal-font selection easier.
- [ ] Improve confidence calibration and error reporting without hiding failures.

## Later: expand the model, not just the marketing

- [ ] Prototype a line-level recognizer with CTC and a documented training dataset.
- [ ] Evaluate text detection, column reading order, and wider character coverage.
- [ ] Investigate packaging for additional operating systems.
- [ ] Benchmark GPU/NPU options only after compatibility and end-to-end gains are demonstrated.

Handwriting, multilingual OCR, robust scene text, and accelerator support are **not current capabilities**. Preserve the small offline baseline while exploring larger architectures in clearly labeled experiments.
