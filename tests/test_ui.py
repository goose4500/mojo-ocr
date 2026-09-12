import http.client
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ui import UIServer, MAX_UPLOAD


class UITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = UIServer(("127.0.0.1", 0), ROOT / "models/print-v1.npz", self.temp.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=30)
        conn.request(method, path, body, headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def test_page_and_security_boundaries(self):
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"From pixels", body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        status, _, body = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        token = json.loads(body)["token"]
        self.assertEqual(token, self.server.token)
        self.assertEqual(
            self.request("GET", "/api/status", headers={"Host": "evil.example"})[0], 403
        )
        self.assertEqual(self.request("POST", "/api/clear")[0], 403)
        self.assertEqual(
            self.request(
                "POST",
                "/api/clear",
                headers={"X-OCR-Token": token, "Origin": "https://evil.example"},
            )[0],
            403,
        )
        self.assertEqual(self.request("GET", "/files/../../native.py")[0], 404)
        self.assertEqual(self.request("GET", "/native.py")[0], 404)

    def test_upload_export_and_clear(self):
        source = (ROOT / "examples/note.png").read_bytes()
        headers = {"X-OCR-Token": self.server.token, "Content-Type": "application/octet-stream"}
        status, _, body = self.request(
            "POST", "/api/ocr?" + urlencode({"name": "../note.png", "dpi": 150}), source, headers
        )
        self.assertEqual(status, 200, body)
        data = json.loads(body)
        self.assertEqual(data["name"], "note.png")
        self.assertEqual(len(data["pages"]), 1)
        self.assertIn("Save this note", data["pages"][0]["text"])
        self.assertIn("Budget: $42.75", data["pages"][0]["text"])
        self.assertEqual(self.request("GET", data["pages"][0]["preview"])[0], 200)
        status, headers_out, pdf = self.request("GET", data["pdf"])
        self.assertEqual(status, 200)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn("attachment", headers_out["Content-Disposition"])
        self.assertFalse(list(Path(self.temp.name).glob("*/input*")))
        from reportlab.pdfgen.canvas import Canvas

        buffer = io.BytesIO()
        canvas = Canvas(buffer, pagesize=(400, 250))
        for text in ["First page", "Second page"]:
            canvas.setFont("Courier", 20)
            canvas.drawString(25, 180, text)
            canvas.showPage()
        canvas.save()
        status, _, body = self.request(
            "POST", "/api/ocr?name=two-pages.pdf", buffer.getvalue(), headers
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(len(json.loads(body)["pages"]), 2)
        self.assertEqual(self.request("POST", "/api/clear", headers=headers)[0], 200)
        self.assertEqual(self.request("GET", data["pdf"])[0], 404)
        self.assertFalse(list(Path(self.temp.name).iterdir()))

    def test_invalid_upload_and_busy(self):
        headers = {"X-OCR-Token": self.server.token}
        self.assertEqual(
            self.request("POST", "/api/ocr?name=test.png", b"not an image", headers)[0], 400
        )
        self.assertFalse(list(Path(self.temp.name).iterdir()))
        self.assertEqual(self.request("POST", "/api/ocr?name=test.exe", b"x", headers)[0], 400)
        self.assertEqual(self.request("POST", "/api/ocr?name=test.png", b"", headers)[0], 413)
        huge = headers | {"Content-Length": str(MAX_UPLOAD + 1)}
        self.assertEqual(self.request("POST", "/api/ocr?name=test.png", b"", huge)[0], 413)
        with self.server.work_lock:
            self.assertEqual(self.request("POST", "/api/clear", headers=headers)[0], 409)


if __name__ == "__main__":
    unittest.main()
