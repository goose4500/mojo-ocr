#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
# Prefer a compiler installed in the project environment; fall back to PATH.
export PATH="$PWD/.venv/bin:$PATH"
command -v mojo >/dev/null || { echo 'Install Mojo 1.0 first; see README.md#start-here' >&2; exit 1; }
mojo --version | grep -q 'Mojo 1\.0\.0 ' || { echo 'This project targets Mojo 1.0.0.' >&2; exit 1; }
command -v uv >/dev/null || { echo 'Install uv first: https://docs.astral.sh/uv/' >&2; exit 1; }
[[ -x .venv/bin/python ]] || uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
# Replace atomically; do not truncate a shared library another process is using.
mojo build kernels.mojo --emit shared-lib -o libocr.build.so
mv libocr.build.so libocr.so
printf '\nReady. Try: ./ocr read image.png\nTrain: ./ocr train --model models/my-model.npz\nTests: .venv/bin/python -m unittest discover -s tests -v\n'
