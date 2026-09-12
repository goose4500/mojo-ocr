# Third-party notices and provenance

The project's MIT license applies to original project material, including its scratch-trained baseline and synthetic examples. It does **not** relicense external dependencies, fonts, compilers, or their bundled components. Refer to the exact installed distributions for authoritative license texts and notices before redistribution.

## Dependencies

- **Mojo compiler and standard library** — [Modular](https://github.com/modular/modular); distributed under their upstream terms, not this project's MIT grant.
- **NumPy** — [NumPy licensing](https://numpy.org/doc/stable/license.html), including notices for bundled numerical libraries.
- **SciPy** — [SciPy](https://github.com/scipy/scipy/blob/main/LICENSE.txt), including bundled-library notices.
- **Pillow** — [Pillow](https://github.com/python-pillow/Pillow/blob/main/LICENSE), including image codec notices.
- **pypdfium2 / PDFium** — [pypdfium2 licensing](https://github.com/pypdfium2-team/pypdfium2#licensing); the Python binding and bundled PDFium have distinct terms and third-party notices.
- **ReportLab** — [ReportLab](https://www.reportlab.com/), including its distribution's license and bundled font notices.
- **charset-normalizer** — [charset-normalizer](https://github.com/jawah/charset_normalizer/blob/master/LICENSE).
- **Ruff** (development only) — [Ruff](https://github.com/astral-sh/ruff/blob/main/LICENSE).
- **uv**, GitHub Actions, and optional Prettier are development infrastructure, not bundled OCR code.

## Fonts and synthetic material

The baseline was rendered from locally installed **DejaVu** and **Liberation** fonts. The unseen-font evaluation used **GNU FreeFont**. The original tests/examples use DejaVu Sans Mono. Font programs are **not included** in this repository. Their licensing and copyright notices remain with the installed font distributions:

- [DejaVu fonts](https://dejavu-fonts.github.io/License.html)
- [Liberation fonts](https://github.com/liberationfonts/liberation-fonts)
- [GNU FreeFont](https://www.gnu.org/software/freefont/license.html)

The baseline contains model weights, not copied font programs. Synthetic example passages were authored for this project. No pretrained neural weights, scraped documents, or personal datasets are included. Review font/data terms when generating or redistributing your own training material; do not assume all fonts share these terms.

The original scan-mark SVG and banner are project artwork under MIT. They do not incorporate Modular's official Mojo logo. References to Mojo, Modular, and Qualcomm describe technology, not sponsorship or endorsement.
