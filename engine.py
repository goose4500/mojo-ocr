"""Reusable OCR API. All recognition uses the scratch-trained Mojo model."""

from pathlib import Path
from contextlib import closing
import time
import base64
import hashlib
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw
from imaging import MAX_PIXELS, feature, prepare, segment
from native import ALPHABET, D, Model


class OCR:
    def __init__(self, model):
        self.model = Model.load(model)
        self.model_info = {
            "path": str(Path(model).resolve()),
            "sha256": hashlib.sha256(Path(model).read_bytes()).hexdigest(),
            "backend": "Mojo 1.0 CPU float32",
            "version": self.model.metadata["version"],
        }

    def _split_touching(self, mask, line):
        """Try low-ink cuts of wide blobs; accept only strong two-glyph evidence."""
        refined, features = [], []
        for x0, y0, x1, y1 in line.glyphs:
            crop = mask[y0:y1, x0:x1]
            h, w = crop.shape
            labels, _ = ndimage.label(crop, structure=np.ones((3, 3)))
            components = ndimage.find_objects(labels)
            tall = [i + 1 for i, s in enumerate(components) if s[0].stop - s[0].start >= h * 0.45]
            if 2 <= len(tall) <= 4:
                # Kerning can overlap x-ranges without connecting the actual ink.
                groups = {i: [i] for i in tall}
                for i, s in enumerate(components, 1):
                    if i not in groups:
                        center = (s[1].start + s[1].stop) / 2
                        nearest = min(
                            tall,
                            key=lambda k: abs(
                                center
                                - (components[k - 1][1].start + components[k - 1][1].stop) / 2
                            ),
                        )
                        groups[nearest].append(i)
                pieces = []
                for group in groups.values():
                    isolated = np.isin(labels, group)
                    columns = np.flatnonzero(isolated.any(axis=0))
                    a, b = int(columns[0]), int(columns[-1]) + 1
                    pieces.append(((x0 + a, y0, x0 + b, y1), feature(isolated[:, a:b])))
                for box, vector in sorted(pieces, key=lambda item: item[0][0]):
                    refined.append(box)
                    features.append(vector)
                continue
            if w < h * 0.5 or w > h * 2.5:
                refined.append((x0, y0, x1, y1))
                features.append(feature(crop))
                continue
            lo, hi = max(2, int(h * 0.16)), min(w - 2, w - int(h * 0.16))
            cuts = sorted(
                range(lo, hi), key=lambda k: (int(crop[:, k - 1 : k + 1].sum()), abs(k - w / 2))
            )[:12]
            feats = [feature(crop)]
            for k in cuts:
                feats.extend([feature(crop[:, :k]), feature(crop[:, k:])])
            p = self.model.predict(np.stack(feats))
            full = -np.log(max(float(p[0].max()), 1e-9)) + max(0, w / h - 0.85) * 3
            best, cut = full, None
            for i, k in enumerate(cuts):
                a, b = float(p[1 + 2 * i].max()), float(p[2 + 2 * i].max())
                score = -np.log(max(a * b, 1e-9)) + 0.75
                if a > 0.8 and b > 0.8 and score < best:
                    best, cut = score, k
            if cut is None:
                refined.append((x0, y0, x1, y1))
                features.append(feature(crop))
            else:
                refined.extend([(x0, y0, x0 + cut, y1), (x0 + cut, y0, x1, y1)])
                features.extend([feature(crop[:, :cut]), feature(crop[:, cut:])])
        line.glyphs = refined
        line.features = features
        line.gaps = [0] + [refined[i][0] - refined[i - 1][2] for i in range(1, len(refined))]

    def image(
        self,
        image,
        *,
        rotate=0,
        deskew=False,
        threshold=None,
        adaptive=False,
        whitelist=None,
        min_confidence=0.6,
        space_factor=1.0,
        collect_features=False,
    ):
        if whitelist is not None and (not whitelist or any(c not in ALPHABET for c in whitelist)):
            raise ValueError("Whitelist must contain non-space printable ASCII characters")
        tick = time.perf_counter()
        processed, mask, skew = prepare(image, rotate, deskew, threshold, adaptive)
        lines = segment(mask)
        for line in lines:
            self._split_touching(mask, line)
        boxes = [b for line in lines for b in line.glyphs]
        x = (
            np.stack([f for line in lines for f in line.features])
            if boxes
            else np.empty((0, D), np.float32)
        )
        probabilities = self.model.predict(x)
        allowed = (
            np.array([c in whitelist for c in ALPHABET])
            if whitelist
            else np.ones(len(ALPHABET), bool)
        )
        result_lines, cursor = [], 0
        left_edge = min((line.box[0] for line in lines), default=0)
        for line in lines:
            widths = [b[2] - b[0] for b in line.glyphs]
            gaps = np.array(line.gaps[1:])
            height = line.box[3] - line.box[1]
            base_gap = float(np.percentile(gaps, 35)) if len(gaps) else 0
            space_at = (
                max(height * 0.22, base_gap * 2, float(np.median(widths)) * 0.45) * space_factor
            )
            centers = np.array([(b[0] + b[2]) / 2 for b in line.glyphs])
            advances = np.diff(centers)
            pitch = 0.0
            if len(advances) >= 7:
                candidate = float(np.median(advances[advances <= np.percentile(advances, 65)]))
                multiples = np.maximum(1, np.round(advances / candidate))
                candidate = float(np.median(advances / multiples))
                if (
                    np.mean(np.abs(advances / candidate - np.round(advances / candidate)) < 0.18)
                    >= 0.9
                ):
                    pitch = candidate
            indent = max(0, round((line.box[0] - left_edge) / pitch)) if pitch else 0
            chars, text = [], " " * indent
            for glyph_index, (box, gap) in enumerate(zip(line.glyphs, line.gaps)):
                p = probabilities[cursor]
                best = int(np.argmax(np.where(allowed, p, -1)))
                top = np.argsort(p)[-3:][::-1]
                conf = float(p[best])  # NOT renormalized after whitelisting.
                ch = ALPHABET[best]
                spaces = 0
                if glyph_index:
                    spaces = (
                        max(0, round(advances[glyph_index - 1] / (pitch * space_factor)) - 1)
                        if pitch
                        else int(gap > space_at)
                    )
                space = spaces > 0
                text += " " * spaces + ch
                chars.append(
                    {
                        "text": ch,
                        "box": list(box),
                        "confidence": conf,
                        "uncertain": conf < min_confidence,
                        "space_before": space,
                        "spaces_before": spaces,
                        "alternatives": [
                            {"text": ALPHABET[k], "confidence": float(p[k])} for k in top
                        ],
                    }
                )
                if collect_features:
                    chars[-1]["feature"] = base64.b64encode(
                        np.round(x[cursor] * 255).astype(np.uint8).tobytes()
                    ).decode()
                cursor += 1
            result_lines.append(
                {
                    "text": text,
                    "box": list(line.box),
                    "characters": chars,
                    "confidence": float(np.mean([c["confidence"] for c in chars])),
                }
            )
        result = {
            "text": "\n".join(line["text"] for line in result_lines),
            "model": self.model_info,
            "width": processed.width,
            "height": processed.height,
            "rotation": rotate,
            "deskew_angle": skew,
            "lines": result_lines,
            "uncertain_characters": sum(
                c["uncertain"] for line in result_lines for c in line["characters"]
            ),
            "seconds": time.perf_counter() - tick,
            "warnings": [
                "Experimental printed-ASCII OCR. Confidence is uncalibrated; verify important numbers."
            ],
        }
        return result, processed, mask


def pages(path, dpi=150, max_pages=100):
    """Yield pages incrementally; close native PDF handles even on errors."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium

        with pdfium.PdfDocument(str(path)) as doc:
            if len(doc) > max_pages:
                raise ValueError(
                    f"PDF has {len(doc)} pages; limit is {max_pages}. Increase --max-pages explicitly."
                )
            for i in range(len(doc)):
                with closing(doc[i]) as page:
                    w, h = page.get_size()
                    if w * h * (dpi / 72) ** 2 > MAX_PIXELS:
                        raise ValueError("Rendered PDF page too large; lower --dpi")
                    bitmap = page.render(scale=dpi / 72)
                    try:
                        yield i + 1, bitmap.to_pil().copy()
                    finally:
                        bitmap.close()
    else:
        with Image.open(path) as im:
            count = getattr(im, "n_frames", 1)
            if count > max_pages:
                raise ValueError(f"Image has {count} frames; exceeds --max-pages")
            for i in range(count):
                im.seek(i)
                if im.width * im.height > MAX_PIXELS:
                    raise ValueError(
                        "Input frame too large; crop/downsample it with an image editor first"
                    )
                yield i + 1, im.copy()


def overlay(image, result):
    image = image.copy()
    draw = ImageDraw.Draw(image)
    for line in result["lines"]:
        for char in line["characters"]:
            draw.rectangle(char["box"], outline="red" if char["uncertain"] else "green", width=1)
    return image


def distance(a, b):
    """Levenshtein edit distance with O(len(b)) memory."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            row.append(min(row[-1] + 1, previous[j] + 1, previous[j - 1] + (ca != cb)))
        previous = row
    return previous[-1]
