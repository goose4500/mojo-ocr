"""Document preprocessing and explicit, inspectable projection segmentation."""

from dataclasses import dataclass
import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage

WIDTH, HEIGHT = 24, 32
MAX_PIXELS = 24_000_000


def runs(mask):
    edges = np.diff(np.r_[False, np.asarray(mask, bool), False].astype(np.int8))
    return list(zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist()))


def otsu(gray):
    hist = np.bincount(gray.ravel(), minlength=256).astype(float)
    weight = np.cumsum(hist)
    sums = np.cumsum(hist * np.arange(256))
    numerator = (sums[-1] * weight - sums * weight[-1]) ** 2
    denom = weight * (weight[-1] - weight)
    scores = np.divide(numerator, denom, out=np.zeros(256), where=denom > 0)
    return int(np.argmax(scores))


def prepare(image, rotate=0, deskew=False, threshold=None, adaptive=False):
    if image.width * image.height > MAX_PIXELS:
        raise ValueError(f"Image exceeds {MAX_PIXELS:,} pixel limit; crop or downsample it first")
    # Composite alpha on white, not black; respect camera orientation.
    image = ImageOps.exif_transpose(image).convert("RGBA")
    bg = Image.new("RGBA", image.size, "white")
    bg.alpha_composite(image)
    image = bg.convert("RGB")
    if rotate:
        image = image.rotate(rotate, expand=True, fillcolor="white")
    gray = np.asarray(ImageOps.grayscale(image))
    if np.median(gray) < 127:
        gray = 255 - gray
    if adaptive:
        background = ndimage.maximum_filter(gray, size=31)
        gray = np.clip(gray.astype(float) * 255 / np.maximum(background, 1), 0, 255).astype(
            np.uint8
        )
    cutoff = otsu(gray) if threshold is None else threshold
    mask = gray <= cutoff
    if mask.mean() > 0.8 or gray.max() == gray.min():
        mask = np.zeros_like(mask)
    angle = 0.0
    if deskew and mask.any():
        # Bounded +/-3 degree projection search, not orientation detection.
        scale = min(1, 900 / max(mask.shape))
        small = ndimage.zoom(mask.astype(np.uint8), scale, order=0)
        angles = np.arange(-3, 3.01, 0.25)
        scores = []
        for a in angles:
            rows = ndimage.rotate(small, a, reshape=False, order=0).sum(axis=1).astype(float)
            scores.append(float(np.sum(np.diff(rows) ** 2)))
        angle = float(angles[int(np.argmax(scores))])
        if angle:
            image = image.rotate(
                angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white"
            )
            mask = np.asarray(
                Image.fromarray(mask).rotate(angle, expand=True, fillcolor=0), dtype=bool
            )
    return image, mask, angle


def feature(crop):
    """Keep the full line's vertical coordinates; center the glyph horizontally."""
    if crop.ndim != 2 or not crop.size or not crop.any():
        return np.zeros(WIDTH * HEIGHT, np.float32)
    cols = np.flatnonzero(crop.any(axis=0))
    crop = crop[:, cols[0] : cols[-1] + 1]
    h, w = crop.shape
    nh = HEIGHT - 4
    nw = max(1, min(WIDTH - 2, round(w * nh / h)))
    resized = Image.fromarray(crop.astype(np.uint8) * 255).resize(
        (nw, nh), Image.Resampling.BILINEAR
    )
    canvas = np.zeros((HEIGHT, WIDTH), np.float32)
    canvas[2 : 2 + nh, (WIDTH - nw) // 2 : (WIDTH - nw) // 2 + nw] = (
        np.asarray(resized, dtype=np.float32) / 255
    )
    return canvas.ravel()


@dataclass
class Line:
    box: tuple
    glyphs: list
    gaps: list


def segment(mask):
    if not mask.any():
        return []
    labels, _ = ndimage.label(mask)
    components = ndimage.find_objects(labels)
    heights = [s[0].stop - s[0].start for s in components if s and s[0].stop - s[0].start >= 5]
    typical = float(np.median(heights)) if heights else 10
    row_runs = runs(mask.any(axis=1))
    merged = []
    for y0, y1 in row_runs:
        if merged and y0 - merged[-1][1] <= max(2, int(typical * 0.25)):
            merged[-1] = (merged[-1][0], y1)
        else:
            merged.append((y0, y1))
    result = []
    for y0, y1 in merged:
        crop = mask[y0:y1]
        spans = runs(crop.any(axis=0))
        if not spans:
            continue
        boxes = [(x0, y0, x1, y1) for x0, x1 in spans]
        gaps = [0] + [spans[i][0] - spans[i - 1][1] for i in range(1, len(spans))]
        result.append(Line((spans[0][0], y0, spans[-1][1], y1), boxes, gaps))
    return result
