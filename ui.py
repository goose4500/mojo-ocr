"""Loopback-only, single-user browser UI. No additional server dependencies."""

import json
import re
import secrets
import shutil
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app import EXTENSIONS, SearchablePDF
from engine import OCR, overlay, pages
from native import ROOT

MAX_UPLOAD = 25 * 1024 * 1024
MAX_PAGES = 20


class UIServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, model, workspace):
        self.ocr = OCR(model)
        self.workspace = Path(workspace)
        self.token = secrets.token_hex(32)
        self.work_lock = threading.Lock()
        super().__init__(address, Handler)

    def prune(self):
        jobs = sorted(self.workspace.iterdir(), key=lambda p: p.stat().st_mtime)
        for index, job in enumerate(jobs):
            if time.time() - job.stat().st_mtime > 3600 or index < len(jobs) - 9:
                shutil.rmtree(job, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "MojoOCR/0.1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(60)

    def log_message(self, fmt, *args):
        # Do not log document names, result tokens, or text.
        pass

    def send_headers(self, status, content_type, length, download=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.end_headers()

    def json(self, status, value):
        body = json.dumps(value).encode()
        self.send_headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def file(self, path, content_type, download=None):
        try:
            with path.open("rb") as stream:
                self.send_headers(200, content_type, path.stat().st_size, download)
                shutil.copyfileobj(stream, self.wfile)
        except FileNotFoundError:
            self.json(404, {"error": "Result expired or cleared. Run OCR again."})

    def trusted(self, mutation=False):
        port = self.server.server_port
        hosts = {f"localhost:{port}", f"127.0.0.1:{port}"}
        if self.headers_in.get("Host") not in hosts:
            return False
        origin = self.headers_in.get("Origin")
        if origin and origin not in {"http://" + host for host in hosts}:
            return False
        if self.headers_in.get("Sec-Fetch-Site") == "cross-site":
            return False
        return not mutation or secrets.compare_digest(
            self.headers_in.get("X-OCR-Token", ""), self.server.token
        )

    def do_GET(self):
        self.headers_in = self.headers
        if not self.trusted():
            self.json(403, {"error": "Only same-origin localhost requests are allowed."})
            return
        path = urlsplit(self.path).path
        static = {
            "/": ("ui.html", "text/html; charset=utf-8"),
            "/ui.js": ("ui.js", "text/javascript; charset=utf-8"),
            "/ui.css": ("ui.css", "text/css; charset=utf-8"),
            "/example.png": ("examples/note.png", "image/png"),
            "/assets/logo.svg": ("assets/logo.svg", "image/svg+xml"),
        }
        if path == "/favicon.ico":
            self.send_headers(204, "image/x-icon", 0)
        elif path in static:
            name, mime = static[path]
            self.file(ROOT / name, mime)
        elif path == "/api/status":
            self.json(
                200,
                {
                    "ready": True,
                    "token": self.server.token,
                    "model": Path(self.server.ocr.model_info["path"]).name,
                    "max_upload_mb": MAX_UPLOAD // (1024 * 1024),
                    "max_pages": MAX_PAGES,
                },
            )
        else:
            match = re.fullmatch(
                r"/files/([a-f0-9]{32})/(page-\d+(?:-boxes)?\.jpg|result\.json|searchable\.pdf)",
                path,
            )
            if not match:
                self.json(404, {"error": "Not found"})
                return
            job, name = match.groups()
            target = self.server.workspace / job / name
            if target.exists() and time.time() - target.parent.stat().st_mtime > 3600:
                self.json(410, {"error": "Result expired. Run OCR again."})
                return
            mime = (
                "image/jpeg"
                if name.endswith(".jpg")
                else "application/pdf"
                if name.endswith(".pdf")
                else "application/json"
            )
            self.file(target, mime, None if name.endswith(".jpg") else name)

    def do_POST(self):
        self.headers_in = self.headers
        self.close_connection = True
        if not self.trusted(mutation=True):
            self.json(403, {"error": "Invalid local session. Reload the page."})
            return
        url = urlsplit(self.path)
        if url.path not in {"/api/ocr", "/api/clear"}:
            self.json(404, {"error": "Not found"})
            return
        if not self.server.work_lock.acquire(blocking=False):
            self.json(409, {"error": "OCR is already running. Please wait and try again."})
            return
        job = None
        try:
            if url.path == "/api/clear":
                for item in self.server.workspace.iterdir():
                    shutil.rmtree(item, ignore_errors=True)
                self.json(200, {"cleared": True})
                return
            length = int(self.headers_in.get("Content-Length", "0"))
            if not 0 < length <= MAX_UPLOAD:
                self.json(413, {"error": "Choose a non-empty file smaller than 25 MiB."})
                return
            query = parse_qs(url.query)

            def get(key, default=""):
                return query.get(key, [default])[0]

            name = get("name").replace("\\", "/").split("/")[-1][:200]
            suffix = Path(name).suffix.lower()
            if suffix not in EXTENSIONS:
                raise ValueError("Choose a PNG, JPG, WebP, BMP, TIFF, or PDF file.")
            dpi, rotate = int(get("dpi", "150")), int(get("rotate", "0"))
            if dpi not in {150, 200, 300} or rotate not in {0, 90, 180, 270}:
                raise ValueError("Invalid image settings")
            self.server.prune()
            key = secrets.token_hex(16)
            job = self.server.workspace / key
            job.mkdir()
            source = job / ("input" + suffix)
            with source.open("wb") as stream:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(remaining, 1024 * 1024))
                    if not chunk:
                        raise ValueError("Upload interrupted. Please retry.")
                    stream.write(chunk)
                    remaining -= len(chunk)
            start = time.perf_counter()
            pdf = SearchablePDF(job / "searchable.pdf", dpi)
            results = []
            for number, image in pages(source, dpi=dpi, max_pages=MAX_PAGES):
                result, processed, _ = self.server.ocr.image(
                    image,
                    rotate=rotate,
                    deskew=get("deskew") == "1",
                    adaptive=get("adaptive") == "1",
                    whitelist="0123456789.,-$+%()/" if get("mode") == "numbers" else None,
                )
                pdf.add(processed, result)
                marked = overlay(processed, result)
                for picture, tail in [(processed, ""), (marked, "-boxes")]:
                    picture.thumbnail((1400, 1400))
                    picture.save(job / f"page-{number}{tail}.jpg", quality=88)
                result.update(
                    page=number,
                    preview=f"/files/{key}/page-{number}.jpg",
                    overlay=f"/files/{key}/page-{number}-boxes.jpg",
                )
                results.append(result)
            pdf.close()
            source.unlink()  # Keep derivatives only until cleared/server exit.
            data = {
                "name": name,
                "pages": results,
                "seconds": time.perf_counter() - start,
                "pdf": f"/files/{key}/searchable.pdf",
                "json": f"/files/{key}/result.json",
            }
            (job / "result.json").write_text(json.dumps(data, indent=2))
            self.json(200, data)
        except (BrokenPipeError, ConnectionResetError):
            if job:
                shutil.rmtree(job, ignore_errors=True)
        except Exception as exc:
            if job:
                shutil.rmtree(job, ignore_errors=True)
            self.json(400, {"error": str(exc) or "Unable to read this file."})
        finally:
            self.server.work_lock.release()


def serve(args):
    if not 1 <= args.port <= 65535:
        raise ValueError("--port must be between 1 and 65535")
    with tempfile.TemporaryDirectory(prefix="mojo-ocr-") as workspace:
        server = UIServer(("127.0.0.1", args.port), args.model, workspace)
        print(
            f"Mojo OCR → http://localhost:{server.server_port}\nLocal only. Ctrl+C stops the server and deletes temporary results.",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
            # Wait for an active upload/recognition before removing its workspace.
            with server.work_lock:
                pass
