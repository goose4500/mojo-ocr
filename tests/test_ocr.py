import base64
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native import Model, ALPHABET, D, H, C, W2, B1, B2
from imaging import feature, prepare, runs, segment
from engine import OCR, pages, distance
from app import correction_data
from training import synthesize, DEFAULT_FONTS


def reference_predict(x, w):
    hidden = np.maximum(x @ w[:W2].reshape(H, D).T + w[B1:B2], 0)
    z = hidden @ w[W2:B1].reshape(C, H).T + w[B2:]
    p = np.exp(z - z.max(axis=1, keepdims=True))
    return hidden, p / p.sum(axis=1, keepdims=True)


def rendered(text, size=28):
    image = Image.new("RGB", (760, 220), "white")
    font = ImageFont.truetype(DEFAULT_FONTS[2], size)
    ImageDraw.Draw(image).multiline_text((20, 20), text, font=font, fill="black", spacing=16)
    return image


class NativeTests(unittest.TestCase):
    def test_forward_matches_numpy(self):
        model = Model(seed=7)
        x = np.random.default_rng(4).random((7, D), dtype=np.float32)
        _, expected = reference_predict(x, model.weights)
        actual = model.predict(x)
        np.testing.assert_allclose(actual, expected, rtol=3e-5, atol=1e-7)
        np.testing.assert_allclose(actual.sum(axis=1), 1, atol=1e-6)
        self.assertEqual(model.predict(np.empty((0, D), np.float32)).shape, (0, C))

    def test_backprop_and_momentum_match_numpy(self):
        model = Model(seed=9)
        rng = np.random.default_rng(3)
        x = rng.random((3, D), dtype=np.float32)
        y = np.array([0, 20, 93], np.int64)
        order = np.array([2, 0, 1], np.int64)
        expected = model.weights.copy()
        velocity = np.zeros_like(expected)
        lr, momentum, decay = 0.002, 0.8, 1e-5
        losses = []
        for idx in order:
            h, p = reference_predict(x[idx : idx + 1], expected)
            losses.append(-np.log(p[0, y[idx]]))
            dz = p[0].copy()
            dz[y[idx]] -= 1
            dh = (dz @ expected[W2:B1].reshape(C, H)) * (h[0] > 0)
            grad = np.empty_like(expected)
            grad[:W2] = np.outer(dh, x[idx]).ravel() + decay * expected[:W2]
            grad[W2:B1] = np.outer(dz, h[0]).ravel() + decay * expected[W2:B1]
            grad[B1:B2], grad[B2:] = dh, dz
            velocity = momentum * velocity + grad
            expected -= lr * velocity
        loss = model.epoch(x, y, order, lr, momentum, decay)
        np.testing.assert_allclose(model.weights, expected, rtol=2e-4, atol=2e-7)
        np.testing.assert_allclose(model.velocity, velocity, rtol=2e-4, atol=2e-6)
        self.assertAlmostEqual(loss, float(np.mean(losses)), places=4)

    def test_sgd_learns_and_validation_rejects_bad_buffers(self):
        model = Model()
        x = np.zeros((8, D), np.float32)
        x[:4, :20], x[4:, 20:40] = 1, 1
        y = np.array([0] * 4 + [1] * 4, np.int64)
        order = np.arange(8, dtype=np.int64)
        first = model.epoch(x, y, order)
        for _ in range(20):
            last = model.epoch(x, y, order)
        self.assertLess(last, first * 0.2)
        np.testing.assert_array_equal(model.predict(x).argmax(axis=1), y)
        for bad in [np.zeros((8, D - 1), np.float32), np.full((8, D), np.nan, np.float32)]:
            with self.assertRaises(ValueError):
                model.predict(bad)
        for bad_y in [y.astype(np.int32), np.full(8, C, np.int64)]:
            with self.assertRaises(ValueError):
                model.epoch(x, bad_y, order)
        with self.assertRaises(ValueError):
            model.epoch(x, y, np.full(8, 8, np.int64))
        with self.assertRaises(ValueError):
            model.epoch(x[:, ::-1], y, order)

    def test_checkpoint_and_synthesis(self):
        model = Model(seed=5)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "model.npz"
            model.save(path, note="local test")
            loaded = Model.load(path)
            np.testing.assert_array_equal(loaded.weights, model.weights)
            self.assertEqual(loaded.metadata["note"], "local test")
            np.savez(path, weights=model.weights, metadata="{}")
            with self.assertRaises(ValueError):
                Model.load(path)
        x, y = synthesize(1, [DEFAULT_FONTS[0]], 9)
        xx, yy = synthesize(1, [DEFAULT_FONTS[0]], 9)
        np.testing.assert_array_equal(x, xx)
        np.testing.assert_array_equal(y, yy)
        self.assertEqual(x.shape, (C, D))


class ImagingTests(unittest.TestCase):
    def test_runs_and_blank_images(self):
        self.assertEqual(runs([1, 1, 0, 1]), [(0, 2), (3, 4)])
        for color in ["white", "black"]:
            _, mask, _ = prepare(Image.new("RGB", (30, 30), color))
            self.assertFalse(mask.any())
            self.assertEqual(segment(mask), [])
        _, mask, _ = prepare(Image.new("RGBA", (20, 20), (0, 0, 0, 0)))
        self.assertFalse(mask.any())
        self.assertEqual(feature(np.zeros((0, 0), bool)).shape, (D,))

    def test_dark_mode_rotation_deskew(self):
        image = rendered("Private notes\nRoom 204")
        _, normal, _ = prepare(image)
        _, dark, _ = prepare(ImageOps.invert(image))
        np.testing.assert_array_equal(normal, dark)
        rotated, _, _ = prepare(image, rotate=90)
        self.assertEqual(rotated.size, image.size[::-1])
        _, mask, angle = prepare(image.rotate(2, fillcolor="white"), deskew=True)
        self.assertLess(abs(angle + 2), 0.75)
        self.assertEqual(len(segment(mask)), 2)

    def test_edit_distance(self):
        self.assertEqual(distance("kitten", "sitting"), 3)
        self.assertEqual(distance("", "abc"), 3)
        self.assertEqual(distance(["one", "two"], ["one"]), 1)


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr = OCR(ROOT / "models/print-v1.npz")

    def cli(self, *args, expected=0):
        result = subprocess.run(
            [sys.executable, str(ROOT / "app.py"), *map(str, args)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def test_independent_note(self):
        truth = "Save this note\nBudget: $42.75\nRoom 204"
        r, _, _ = self.ocr.image(rendered(truth), collect_features=True)
        self.assertLess(distance(truth, r["text"]) / len(truth), 0.08, r["text"])
        self.assertEqual(len(r["lines"]), 3)
        for line in r["lines"]:
            for char in line["characters"]:
                self.assertEqual(len(base64.b64decode(char["feature"])), D)
        blank, _, _ = self.ocr.image(Image.new("RGB", (20, 20), "white"))
        self.assertEqual(blank["text"], "")
        with self.assertRaises(ValueError):
            self.ocr.image(rendered("123"), whitelist="é")
        r, _, _ = self.ocr.image(rendered("123"), whitelist="123")
        self.assertTrue(set(r["text"]) <= set("123 \n"))

    def test_read_pdf_review_index_search(self):
        import pypdfium2 as pdfium

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, out, db = root / "note.png", root / "out", root / "search.db"
            rendered("Private notes\nRoom 204").save(source)
            self.cli("read", source, "--out", out, "--pdf", "--review", "--overlay")
            result = json.loads(next(out.glob("*.json")).read_text())
            self.assertIn("Private notes", result["pages"][0]["text"])
            self.assertTrue(list(out.glob("*.overlay.png")))
            review = next(out.glob("*.review.html")).read_text()
            self.assertIn("Download corrections.json", review)
            self.assertNotIn("https://", review)
            pdf = next(out.glob("*.pdf"))
            with pdfium.PdfDocument(str(pdf)) as doc:
                with closing(doc[0]) as page:
                    with closing(page.get_textpage()) as text:
                        self.assertIn("Private notes", text.get_text_range())
            rendered_pages = list(pages(pdf))
            self.assertEqual(len(rendered_pages), 1)
            self.cli("read", pdf, "--json")
            self.cli("index", source, "--db", db)
            self.cli("index", source, "--db", db)
            with closing(sqlite3.connect(db)) as connection:
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM documents").fetchone()[0], 1
                )
            self.assertIn("Room [204]", self.cli("search", "204", "--db", db).stdout)
            # A later unreadable input must not wipe previous successfully indexed text.
            source.write_bytes(b"not an image")
            self.cli("index", source, "--db", db, expected=1)
            self.assertIn("Room [204]", self.cli("search", "204", "--db", db).stdout)
            self.cli("read", root / "missing.png", expected=1)

    def test_multipage_and_corrections(self):
        from reportlab.pdfgen.canvas import Canvas

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "input.pdf"
            canvas = Canvas(str(pdf), pagesize=(400, 250))
            for text in ["Page one", "Page two"]:
                canvas.setFont("Courier", 20)
                canvas.drawString(30, 200, text)
                canvas.showPage()
            canvas.save()
            self.assertEqual(len(list(pages(pdf))), 2)
            with self.assertRaises(ValueError):
                list(pages(pdf, max_pages=1))
            self.cli("read", pdf, "--out", root / "out", "--pdf")
            data = {
                "version": 1,
                "samples": [{"label": "A", "feature": base64.b64encode(bytes(D)).decode()}],
            }
            path = root / "corrections.json"
            path.write_text(json.dumps(data))
            x, y = correction_data([path])
            self.assertEqual(x.shape, (1, D))
            self.assertEqual(y[0], ALPHABET.index("A"))
            data["samples"][0]["feature"] = "AA=="
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                correction_data([path])


if __name__ == "__main__":
    unittest.main()
