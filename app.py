#!/usr/bin/env python3
"""Mojo OCR: private OCR, built from scratch in Mojo."""

import argparse
import base64
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import numpy as np
from PIL import Image
from engine import OCR, distance, overlay, pages
from native import ALPHABET, D, ROOT

DEFAULT_MODEL = ROOT / "models/print-v1.npz"
EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".pdf"}


def options(args):
    return {
        key: getattr(args, key)
        for key in (
            "rotate",
            "deskew",
            "threshold",
            "adaptive",
            "whitelist",
            "min_confidence",
            "space_factor",
        )
    }


def inputs(paths, recursive=False):
    found = set()
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            found.update(
                p.resolve()
                for p in (path.rglob("*") if recursive else path.glob("*"))
                if p.is_file() and p.suffix.lower() in EXTENSIONS
            )
        elif path.is_file():
            found.add(path.resolve())
        else:
            raise ValueError(f"Input does not exist: {path}")
    if not found:
        raise ValueError("No supported input files found")
    return sorted(found)


def file_pages(path, args, ocr):
    for number, image in pages(path, args.dpi, args.max_pages):
        if args.crop:
            x, y, w, h = args.crop
            if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > image.width or y + h > image.height:
                raise ValueError("Crop must be inside the source image: X Y WIDTH HEIGHT")
            image = image.crop((x, y, x + w, y + h))
        result, processed, mask = ocr.image(
            image, collect_features=getattr(args, "review", False), **options(args)
        )
        result.update(
            source=str(path),
            page=number,
            crop=args.crop,
            coordinate_system="pixels of the cropped/rotated/deskewed output image",
        )
        yield result, processed, mask


class SearchablePDF:
    """New raster PDF with invisible text; never modifies the source document."""

    def __init__(self, path, dpi):
        from reportlab.pdfgen import canvas

        self.canvas = canvas.Canvas(str(path))
        self.scale = 72 / dpi

    def add(self, image, result):
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfbase.pdfmetrics import stringWidth

        c, s = self.canvas, self.scale
        width, height = image.width * s, image.height * s
        c.setPageSize((width, height))
        c.drawImage(ImageReader(image), 0, 0, width, height)
        for line in result["lines"]:
            x0, y0, x1, y1 = line["box"]
            size = max(1, (y1 - y0) * s * 0.85)
            obj = c.beginText(x0 * s, height - y1 * s + size * 0.12)
            obj.setFont("Helvetica", size)
            obj.setTextRenderMode(3)
            natural = stringWidth(line["text"], "Helvetica", size)
            obj.setHorizScale(100 * (x1 - x0) * s / max(natural, 0.01))
            obj.textOut(line["text"])
            c.drawText(obj)
        c.showPage()

    def close(self):
        self.canvas.save()


def png_data(image):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def review_html(path, result, image, mask):
    samples = []
    for line in result["lines"]:
        for c in line["characters"]:
            x0, y0, x1, y1 = c["box"]
            pixels = np.frombuffer(base64.b64decode(c["feature"]), dtype=np.uint8)
            samples.append(
                {
                    "label": c["text"],
                    "feature": base64.b64encode(pixels.tobytes()).decode(),
                    "preview": png_data(Image.fromarray(pixels.reshape(32, 24))),
                    "confidence": round(c["confidence"], 3),
                }
            )
    payload = json.dumps(samples).replace("<", "\\u003c")
    template = """<!doctype html><meta charset="utf-8"><title>Local OCR correction</title>
<style>body{font:17px system-ui;max-width:1100px;margin:2em auto;background:#eee;color:#222} img.page{max-width:100%}.grid{display:flex;flex-wrap:wrap;gap:8px}.card{background:white;padding:8px;display:grid;justify-items:center}input{width:2em;font-size:22px}button{padding:1em;margin:1em}small{font-size:11px}</style>
<h1>Local OCR correction</h1><p>Nothing is uploaded. Fix individual glyph labels below, then export changed labels. This trains the recognizer, not segmentation. A crop containing two letters or missing part of a letter cannot be fixed here. Do not label those crops.</p>
<img class="page" src="data:image/png;base64,__IMAGE__"><p id="message"></p><button id="save">Download corrections.json</button><div class="grid" id="grid"></div>
<script>const samples=__SAMPLES__;const alphabet=__ALPHABET__;
for(const s of samples){const card=document.createElement('label');card.className='card';const img=document.createElement('img');img.src='data:image/png;base64,'+s.preview;img.width=48;img.height=64;const input=document.createElement('input');input.value=s.label;input.maxLength=1;input.setAttribute('aria-label','Correct glyph '+s.label);const small=document.createElement('small');small.textContent='score '+s.confidence;card.append(img,input,small);document.getElementById('grid').append(card);s.input=input;}
document.getElementById('save').onclick=()=>{const changed=[];for(const s of samples){const label=s.input.value;if(label!==s.label){if(label.length!==1||!alphabet.includes(label)){document.getElementById('message').textContent='Each changed label must be one printable ASCII character (not space).';return;}changed.push({label,feature:s.feature});}}const blob=new Blob([JSON.stringify({version:1,samples:changed})],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='corrections.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);document.getElementById('message').textContent='Exported '+changed.length+' changed glyphs.';};</script>"""
    path.write_text(
        template.replace("__IMAGE__", png_data(image))
        .replace("__SAMPLES__", payload)
        .replace("__ALPHABET__", json.dumps(ALPHABET).replace("<", "\\u003c"))
    )


def correction_data(paths):
    x, y = [], []
    for path in paths:
        data = json.loads(Path(path).read_text())
        if data.get("version") != 1:
            raise ValueError("Unsupported correction format")
        for sample in data["samples"]:
            label = sample["label"]
            pixels = np.frombuffer(
                base64.b64decode(sample["feature"], validate=True), dtype=np.uint8
            )
            if len(label) != 1 or label not in ALPHABET or pixels.shape != (D,):
                raise ValueError(f"Invalid correction in {path}")
            x.append(pixels.astype(np.float32) / 255)
            y.append(ALPHABET.index(label))
    return np.asarray(x, np.float32).reshape(-1, D), np.asarray(y, np.int64)


def extract(args):
    files = inputs(args.inputs, args.recursive)
    out = Path(args.out) if args.out else None
    if (args.pdf or args.review or args.overlay) and out is None:
        raise ValueError("--pdf/--review/--overlay require --out DIRECTORY")
    if out:
        out.mkdir(parents=True, exist_ok=True)
    ocr, failures = OCR(args.model), 0
    for source in files:
        stem = source.stem + "-" + hashlib.sha256(str(source).encode()).hexdigest()[:8]
        pdf = None
        try:
            if args.pdf:
                pdf = SearchablePDF(out / f"{stem}.searchable.pdf.tmp", args.dpi)
            results = []
            for result, image, mask in file_pages(source, args, ocr):
                results.append(result)
                if out:
                    prefix = out / f"{stem}.p{result['page']:04d}"
                    if args.overlay:
                        overlay(image, result).save(str(prefix) + ".overlay.png")
                    if args.review:
                        review_html(Path(str(prefix) + ".review.html"), result, image, mask)
                if pdf:
                    pdf.add(image, result)
            if pdf:
                pdf.close()
                (out / f"{stem}.searchable.pdf.tmp").replace(out / f"{stem}.searchable.pdf")
            text = "\n\f\n".join(r["text"] for r in results)
            if out:
                (out / f"{stem}.txt").write_text(text + "\n")
                (out / f"{stem}.json").write_text(
                    json.dumps({"source": str(source), "pages": results}, indent=2) + "\n"
                )
                print(f"{source.name}: {len(results)} page(s) → {out / stem}", file=sys.stderr)
            else:
                if len(files) > 1:
                    print(f"=== {source} ===")
                print(json.dumps({"source": str(source), "pages": results}) if args.json else text)
        except Exception as exc:
            failures += 1
            print(f"ERROR {source}: {exc}", file=sys.stderr)
        finally:
            if out:
                (out / f"{stem}.searchable.pdf.tmp").unlink(missing_ok=True)
    return 1 if failures else 0


def connect_index(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5(source UNINDEXED, page UNINDEXED, text)"
    )
    return db


def index(args):
    ocr, failures = OCR(args.model), 0
    with closing(connect_index(args.db)) as db:
        for source in inputs(args.inputs, args.recursive):
            try:
                # Finish OCR first: failed files do not delete their previous index.
                rows = [
                    (str(source), r["page"], r["text"]) for r, _, _ in file_pages(source, args, ocr)
                ]
                with db:
                    db.execute("DELETE FROM documents WHERE source = ?", (str(source),))
                    db.executemany("INSERT INTO documents(source,page,text) VALUES(?,?,?)", rows)
                print(f"Indexed {source}: {len(rows)} page(s)")
            except Exception as exc:
                failures += 1
                print(f"ERROR {source}: {exc}", file=sys.stderr)
    return 1 if failures else 0


def search(args):
    if not Path(args.db).is_file():
        raise ValueError("Index does not exist; run index first")
    # Default is a literal phrase. --fts explicitly opts into FTS5 query syntax.
    query = args.query if args.fts else '"' + args.query.replace('"', '""') + '"'
    with closing(sqlite3.connect(Path(args.db).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute(
            "SELECT source,page,snippet(documents,2,'[',']',' … ',24) FROM documents WHERE documents MATCH ? ORDER BY rank LIMIT ?",
            (query, args.limit),
        ).fetchall()
    for source, page, snippet in rows:
        print(f"{source} (page {page})\n  {snippet}")
    if not rows:
        print("No matches.")
    return 0


def benchmark(args):
    from PIL import ImageDraw, ImageFont, ImageFilter, ImageOps
    from training import DEFAULT_FONTS, HELDOUT_FONTS

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ocr = OCR(args.model)
    cases = {
        "note": "Local OCR on my machine\nKeep documents private and searchable.\nMeeting at 10:30 on September 12.",
        "receipt": "INVOICE 2026-0912\nSubtotal: $128.50\nTax: $10.28\nTOTAL DUE: $138.78",
        "code": "def read_file(path):\n    return open(path).read()\ncount = 42 # local only",
        "contact": "Email: hello@example.com\nPhone: (555) 123-4567\nhttps://example.com/docs",
    }
    rows = []
    for font_path in DEFAULT_FONTS[:5] + HELDOUT_FONTS:
        if not Path(font_path).exists():
            continue
        font = ImageFont.truetype(font_path, 30)
        for name, truth in cases.items():
            for variant in ("clean", "blurred", "dark"):
                image = Image.new("RGB", (900, 230), "white")
                ImageDraw.Draw(image).multiline_text(
                    (25, 25), truth, font=font, fill="black", spacing=15
                )
                if variant == "blurred":
                    image = image.filter(ImageFilter.GaussianBlur(0.6))
                elif variant == "dark":
                    image = ImageOps.invert(image)
                result, _, _ = ocr.image(image)
                edits = distance(truth, result["text"])
                # WER ignores whitespace multiplicity; raw CER intentionally does not.
                words = truth.split()
                row = {
                    "case": name,
                    "font": Path(font_path).name,
                    "unseen_font": font_path in HELDOUT_FONTS,
                    "variant": variant,
                    "truth": truth,
                    "prediction": result["text"],
                    "edits": edits,
                    "characters": len(truth),
                    "cer": edits / len(truth),
                    "word_edits": distance(words, result["text"].split()),
                    "words": len(words),
                    "seconds": result["seconds"],
                }
                rows.append(row)
                if variant == "clean":
                    stem = f"{Path(font_path).stem}-{name}"
                    image.save(out / (stem + ".png"))
                    (out / (stem + ".txt")).write_text(truth + "\n")
    if not rows:
        raise ValueError("No benchmark fonts found")

    def aggregate(items):
        return {
            "pages": len(items),
            "cer": sum(r["edits"] for r in items) / sum(r["characters"] for r in items),
            "wer": sum(r["word_edits"] for r in items) / sum(r["words"] for r in items),
            "median_seconds": float(np.median([r["seconds"] for r in items])),
        }

    report = {
        "description": "Synthetic document benchmark; not a real scanned-document accuracy claim.",
        "model_sha256": hashlib.sha256(Path(args.model).read_bytes()).hexdigest(),
        "overall": aggregate(rows),
        "seen_fonts": aggregate([r for r in rows if not r["unseen_font"]]),
        "unseen_fonts": aggregate([r for r in rows if r["unseen_font"]])
        if any(r["unseen_font"] for r in rows)
        else None,
        "cases": rows,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
    return 0


def evaluate(args):
    ocr = OCR(args.model)
    items = json.loads(Path(args.manifest).read_text())
    root = Path(args.manifest).resolve().parent
    rows = []
    for item in items:
        result = "\n\f\n".join(r["text"] for r, _, _ in file_pages(root / item["image"], args, ocr))
        truth = (root / item["text"]).read_text().rstrip("\n")
        rows.append(
            {
                "image": item["image"],
                "characters": len(truth),
                "edits": distance(truth, result),
                "prediction": result,
                "truth": truth,
            }
        )
    count = sum(r["characters"] for r in rows)
    print(
        json.dumps(
            {
                "cer": sum(r["edits"] for r in rows) / max(count, 1),
                "characters": count,
                "cases": rows,
            },
            indent=2,
        )
    )
    return 0


def positive(value):
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("Must be positive")
    return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--version", action="version", version=f"Mojo OCR {(ROOT / 'VERSION').read_text().strip()}"
    )
    commands = p.add_subparsers(dest="command", required=True)

    def model_option(sub):
        sub.add_argument("--model", type=Path, default=DEFAULT_MODEL)

    def image_options(sub):
        model_option(sub)
        sub.add_argument("--dpi", type=positive, default=150)
        sub.add_argument("--max-pages", type=positive, default=100)
        sub.add_argument(
            "--rotate",
            type=int,
            choices=[0, 90, 180, 270],
            default=0,
            help="Counterclockwise degrees",
        )
        sub.add_argument("--deskew", action="store_true", help="Search +/-3 degrees")
        sub.add_argument(
            "--adaptive",
            action="store_true",
            help="Local background normalization for uneven lighting",
        )
        sub.add_argument("--threshold", type=int, choices=range(256), metavar="0..255")
        sub.add_argument("--crop", nargs=4, type=int, metavar=("X", "Y", "WIDTH", "HEIGHT"))
        sub.add_argument("--whitelist", help="Restrict output, e.g. 0123456789.,-$")
        sub.add_argument("--min-confidence", type=float, default=0.6)
        sub.add_argument(
            "--space-factor", type=float, default=1.0, help="Raise to insert fewer spaces"
        )

    read = commands.add_parser(
        "read", help="Images/PDFs to text, JSON, review pages, searchable PDF"
    )
    image_options(read)
    read.add_argument("inputs", nargs="+")
    read.add_argument("--recursive", action="store_true")
    read.add_argument("--out", type=Path)
    read.add_argument("--json", action="store_true", help="JSON on stdout (without --out)")
    read.add_argument("--pdf", action="store_true")
    read.add_argument("--overlay", action="store_true")
    read.add_argument("--review", action="store_true")
    read.set_defaults(func=extract)
    training = commands.add_parser(
        "train", help="Train from random weights or fine-tune a checkpoint"
    )
    model_option(training)
    training.add_argument("--font", action="append", help="Repeat for multiple local TTF/OTF fonts")
    training.add_argument(
        "--samples", type=positive, default=600, help="Synthetic examples per character"
    )
    training.add_argument("--epochs", type=positive, default=32)
    training.add_argument("--lr", type=float, default=0.003)
    training.add_argument("--seed", type=int, default=42)
    training.add_argument("--resume", type=Path)
    training.add_argument("--corrections", nargs="+", type=Path)
    from training import train

    training.set_defaults(func=train)
    bench = commands.add_parser("benchmark", help="Measure synthetic document CER/WER and latency")
    model_option(bench)
    bench.add_argument("--out", type=Path, default=ROOT / "benchmarks")
    bench.set_defaults(func=benchmark)
    ev = commands.add_parser("evaluate", help="Measure CER on your own labeled images/PDFs")
    image_options(ev)
    ev.add_argument(
        "manifest", type=Path, help="JSON list of {image: path, text: ground-truth .txt path}"
    )
    ev.set_defaults(func=evaluate)
    ui = commands.add_parser("serve", help="Open a private local browser UI")
    model_option(ui)
    ui.add_argument("--port", type=positive, default=8878)

    def start_ui(args):
        from ui import serve

        return serve(args)

    ui.set_defaults(func=start_ui)
    idx = commands.add_parser("index", help="OCR files into a local SQLite FTS5 archive")
    image_options(idx)
    idx.add_argument("inputs", nargs="+")
    idx.add_argument("--recursive", action="store_true")
    idx.add_argument("--db", type=Path, default=ROOT / "archive.sqlite3")
    idx.set_defaults(func=index)
    srch = commands.add_parser("search", help="Search the local OCR archive")
    srch.add_argument("query")
    srch.add_argument("--db", type=Path, default=ROOT / "archive.sqlite3")
    srch.add_argument("--fts", action="store_true")
    srch.add_argument("--limit", type=positive, default=20)
    srch.set_defaults(func=search)
    return p


def main():
    args = parser().parse_args()
    try:
        if hasattr(args, "min_confidence") and not 0 <= args.min_confidence <= 1:
            raise ValueError("--min-confidence must be between 0 and 1")
        if hasattr(args, "space_factor") and not 0 < args.space_factor <= 10:
            raise ValueError("--space-factor must be in (0, 10]")
        return args.func(args) or 0
    except (ValueError, OSError, RuntimeError, sqlite3.Error, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
