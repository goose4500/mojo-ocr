"""Generate small, public synthetic examples; no personal documents needed."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
CASES = {
    "note": ("Save this note\nBudget: $42.75\nRoom 204", "white", "black"),
    "receipt": (
        "INVOICE 2026-0912\nSubtotal: $128.50\nTax: $10.28\nTOTAL DUE: $138.78",
        "white",
        "black",
    ),
    "code": (
        "def read_file(path):\n    return open(path).read()\ncount = 42 # local only",
        "#181818",
        "#eeeeee",
    ),
}
for name, (text, background, ink) in CASES.items():
    image = Image.new("RGB", (800, 240), background)
    ImageDraw.Draw(image).multiline_text(
        (25, 25), text, font=ImageFont.truetype(FONT, 30), fill=ink, spacing=15
    )
    image.save(ROOT / (name + ".png"))
    (ROOT / (name + ".txt")).write_text(text + "\n")
