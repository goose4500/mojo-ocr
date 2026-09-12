# Changelog

Notable user-facing changes are recorded here. Versioning starts with the experimental 0.1.0 foundation; no stable API compatibility is promised yet.

## Unreleased

- Upgrade Pillow from 12.1.1 to 12.3.0 to resolve upstream security advisories. Baseline weights are unchanged; all 84 development-benchmark predictions remain identical.
- Pin current Node 24 GitHub Actions to avoid deprecated action runtimes.

## 0.1.0 — initial foundation

### Added

- Mojo 1.0 float32 SIMD MLP, hand-written backpropagation, and momentum SGD.
- Scratch-trained printed-ASCII baseline, reproducible synthetic data generation, and model card.
- Image/PDF OCR, confidence/coordinate JSON, searchable raster PDFs, and SQLite FTS5 indexing.
- Offline glyph review and correction-based fine-tuning.
- Local browser UI with document previews, text editing, and exports.
- Numerical/application/HTTP tests and recorded development benchmarks.
- Mojo OCR identity, MIT license, contributor/security guides, issue templates, and Linux ARM64/x86-64 CI.

### Known limitations

Printed ASCII only; unreliable on unfamiliar fonts, ligatures, handwriting, photographs, and complex layouts. CPU execution only. The development benchmark is not a blind real-document accuracy estimate. See `MODEL_CARD.md`.
