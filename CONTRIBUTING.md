# Contributing to Mojo OCR

Thanks for helping build a useful, inspectable local OCR toolkit. Start with a small issue or pull request; discuss architectural changes before a large rewrite.

## Development setup

Use Linux (ARM64 or x86-64), Python 3.13, uv, and Mojo 1.0.0. See the [README](README.md#start-here) for compiler installation.

```bash
sudo apt-get install fonts-dejavu-core fonts-liberation fonts-freefont-ttf
./setup.sh
uv pip install --python .venv/bin/python -r requirements-dev.txt
```

Then:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m unittest discover -s tests -v
node --check ui.js  # Optional locally; CI checks browser-script syntax.
```

Run `.venv/bin/ruff format .` to format Python. Rebuild with `./setup.sh` after changing `kernels.mojo`. Restart the UI server after Python changes; reload the browser after HTML/CSS/JS changes. Frontend files can be formatted with `npx prettier@3.6.2 --write ui.html ui.css ui.js`; no Node dependencies are needed at runtime.

## Pull requests

1. Branch from `main`; use a focused name such as `fix/pdf-page-limits`.
2. Keep the change small and explain the user-visible problem.
3. Add a regression test and run the complete suite.
4. Update usage docs and the Unreleased section of `CHANGELOG.md` when behavior changes.
5. Include before/after measurements for recognition or performance claims. Report hardware, compiler, input dimensions, model hash, and timing boundaries.
6. Use a descriptive commit title, e.g. `fix: preserve PDF page ordering` or `feat: add region selection`.

CI builds the native library and runs tests on Linux x86-64 and ARM64. No personal datasets, hardware access, API keys, or self-hosted runners are required. GitHub's main-branch checks, when enabled, use the `Test (ubuntu-24.04)` and `Test (ubuntu-24.04-arm)` jobs.

## Keep the boundaries clear

- Neural arithmetic belongs in Mojo. Python owns I/O, normalization, and buffers.
- Do not replace the from-scratch recognizer with pretrained OCR without an explicit design discussion and transparent labeling.
- Architecture changes require synchronized Mojo/Python dimensions, a new checkpoint format version, rebuilding, retraining, and updated tests.
- Browser text edits are not training labels. Never silently turn them into model updates.
- Do not add background uploads, telemetry, document discovery, or public network binding by default.

## Data and model changes

Use synthetic, public, or explicitly licensed fixtures. **Never submit real receipts, personal screenshots, credentials, correction exports, private paths, or local archives.** Blurring text is not necessarily sufficient anonymization.

Keep personal work in ignored `inputs/`, `data/`, or `output/`. Extra checkpoints in `models/` are ignored by default. A baseline-model update must include provenance, exact generation settings, hash, license, evaluation, and a model-card update. Do not overwrite the baseline just to test a training change—pass a separate `--model` path.

The committed benchmark is a development corpus, not an independent test set. Do not optimize against it and then claim blind generalization. Keep new evaluation data separate from training data.

Before committing:

```bash
git diff --check
git diff --cached --stat
git diff --cached
```

## Communication and licensing

Be respectful, constructive, and specific. Critique code and evidence rather than people. Reports involving private/security-sensitive details belong in the [private security channel](SECURITY.md), not public issues.

Contributions are accepted under the project's [MIT license](LICENSE). Only submit material you have the right to license. Third-party code and data require their own attribution and compatible terms. No contributor license agreement is required.
