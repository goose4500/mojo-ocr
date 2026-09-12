# Mojo OCR identity

## Name and positioning

- **Name:** Mojo OCR (capital M; uppercase OCR).
- **Repository / slug:** `mojo-ocr`.
- **Tagline:** Private OCR, built from scratch in Mojo.
- **Short description:** Local-first, from-scratch OCR with Mojo-native training/inference, a browser workspace, and image/PDF tools.
- **Tone:** useful, plain-spoken, privacy-conscious, and honest about limitations.

Use “Mojo OCR” in UI titles, documentation, releases, and repository metadata. Use `./ocr` for the existing command; do not rename the CLI or checkpoint format just for branding.

## Visual identity

- Forest green: `#21684f` (primary).
- Ink: `#263531` (text).
- Paper: `#f5f6f2` (background).
- Muted green: `#718078` (secondary text).
- Original scan-frame/M mark: [`assets/logo.svg`](../assets/logo.svg).
- README banner: [`assets/banner.svg`](../assets/banner.svg).

Use local/system fonts. No external font/CDN calls belong in the runtime interface. Keep the mark legible and do not imply that it is Modular's official logo.

## Claim discipline

Say “trained from random weights,” “Mojo-native neural arithmetic,” and “local-first.” Do not say “100% Mojo”: preprocessing, I/O, and the UI also use Python/JavaScript.

Never present the small synthetic development corpus as universal OCR accuracy. Mention printed ASCII, CPU execution, and experimental status where users make adoption decisions. Do not claim handwriting, multilingual, NPU, or production-grade support before it is implemented and evaluated.

Mojo OCR is an independent community project, not affiliated with or endorsed by Modular, the Mojo language project, or Qualcomm. All original branding assets are included under the repository's MIT license.
