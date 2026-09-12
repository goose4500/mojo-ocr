"""Reproducible local-font data generation; no pretrained weights or downloads."""

import json
import time
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from imaging import feature
from native import ALPHABET, D, Model

DEFAULT_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
]
HELDOUT_FONTS = [
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
]


@lru_cache(maxsize=1024)
def font_at(path, size):
    return ImageFont.truetype(str(path), size)


def synthesize(per_class, fonts, seed):
    if per_class < 1 or not fonts:
        raise ValueError("Need positive samples-per-class and at least one font")
    rng = np.random.default_rng(seed)
    x = np.empty((len(ALPHABET) * per_class, D), np.float32)
    y = np.repeat(np.arange(len(ALPHABET), dtype=np.int64), per_class)
    # Include lowercase-only, uppercase/numeric, ascender and descender lines.
    contexts = [
        "Agjpqy",
        "Agjpqy",
        "Hello",
        "HELLO123",
        "abcdefhiklmnorstuvwxz",
        "aceimnorsuvwxz",
        "Hx$012",
        "Hx@012",
        "Hx(012)",
        "Hx[012]",
        "Hx/012",
        "Hx_012",
        "Hx!012",
        "0123456789",
    ]
    for i, label in enumerate(y):
        ch = ALPHABET[label]
        font = font_at(str(rng.choice(fonts)), int(rng.integers(17, 49)))
        ref = font.getbbox(str(rng.choice(contexts)) + ch)
        bbox = font.getbbox(ch)
        w = max(1, bbox[2] - bbox[0])
        h = max(1, ref[3] - ref[1])
        image = Image.new("L", (w + 8, h + 4), 0)
        ImageDraw.Draw(image).text((4 - bbox[0], 2 - ref[1]), ch, font=font, fill=255)
        if rng.random() < 0.35:
            image = image.filter(ImageFilter.GaussianBlur(float(rng.uniform(0.15, 0.65))))
        mask = np.asarray(image)[2:-2] > int(rng.integers(75, 180))
        # Vary the detected line bounds by a pixel (scan/threshold variation).
        if rng.random() < 0.25:
            mask = np.pad(mask, ((int(rng.integers(0, 2)), int(rng.integers(0, 2))), (0, 0)))
        x[i] = feature(mask)
    return x, y


def evaluate_glyphs(model, x, y):
    p = model.predict(x)
    pred = p.argmax(axis=1)
    wrong = np.flatnonzero(pred != y)
    confusion = {}
    for i in wrong:
        pair = ALPHABET[y[i]] + " → " + ALPHABET[pred[i]]
        confusion[pair] = confusion.get(pair, 0) + 1
    return {
        "samples": len(y),
        "accuracy": float(np.mean(pred == y)),
        "cross_entropy": float(-np.log(np.maximum(p[np.arange(len(y)), y], 1e-12)).mean()),
        "top_confusions": sorted(confusion.items(), key=lambda kv: -kv[1])[:20],
    }


def train(args):
    fonts = args.font or [f for f in DEFAULT_FONTS if Path(f).exists()]
    for f in fonts:
        if not Path(f).is_file():
            raise ValueError(f"Font not found: {f}")
    print(
        f"Generating {args.samples * len(ALPHABET):,} training glyphs from {len(fonts)} fonts...",
        flush=True,
    )
    x, y = synthesize(args.samples, fonts, args.seed)
    vx, vy = synthesize(max(10, args.samples // 8), fonts, args.seed + 1)
    if args.corrections:
        from app import correction_data

        cx, cy = correction_data(args.corrections)
        if len(cy):
            # Oversample local examples but keep synthetic replay to limit forgetting.
            repeat = max(1, min(30, len(y) // (5 * len(cy))))
            x = np.concatenate([x] + [cx] * repeat)
            y = np.concatenate([y] + [cy] * repeat)
            print(f"Added {len(cy)} corrected glyphs, repeated {repeat} times", flush=True)
    model = Model.load(args.resume) if args.resume else Model(seed=args.seed)
    rng = np.random.default_rng(args.seed + 2)
    best, history = float("inf"), []
    start = time.perf_counter()
    for epoch in range(args.epochs):
        tick = time.perf_counter()
        lr = args.lr * (0.15 + 0.85 * (1 - epoch / max(1, args.epochs - 1)))
        loss = model.epoch(x, y, rng.permutation(len(y)).astype(np.int64), lr=lr)
        metrics = evaluate_glyphs(model, vx, vy)
        row = {
            "epoch": epoch + 1,
            "lr": lr,
            "train_loss": loss,
            "validation": metrics,
            "seconds": time.perf_counter() - tick,
        }
        history.append(row)
        print(
            f"epoch {epoch + 1:02d}/{args.epochs}: loss={loss:.4f} val={metrics['accuracy']:.2%} {row['seconds']:.1f}s",
            flush=True,
        )
        if metrics["cross_entropy"] < best:
            best = metrics["cross_entropy"]
            model.save(
                args.model,
                seed=args.seed,
                fonts=fonts,
                samples=len(y),
                best_epoch=epoch + 1,
                validation=metrics,
                trained_from_scratch=not bool(args.resume),
                parent_checkpoint=str(args.resume) if args.resume else None,
            )
    report = {
        "kind": "synthetic isolated glyph validation, NOT document OCR accuracy",
        "seconds": time.perf_counter() - start,
        "history": history,
        "fonts": fonts,
    }
    heldout = [f for f in HELDOUT_FONTS if Path(f).exists() and f not in fonts]
    if heldout:
        hx, hy = synthesize(30, heldout, args.seed + 3)
        report["unseen_fonts"] = heldout
        report["unseen_font_glyphs"] = evaluate_glyphs(Model.load(args.model), hx, hy)
    report_path = Path(args.model).with_suffix(".training.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Saved best checkpoint: {args.model}\nTraining report: {report_path}", flush=True)
