"""Validated NumPy-owned buffers around the private Mojo C ABI."""

import ctypes as ct
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
D, H, C = 768, 128, 94
ALPHABET = "".join(chr(i) for i in range(33, 127))
W2, B1 = H * D, H * D + C * H
B2 = B1 + H
PARAMS = B2 + C
VERSION = 1


def checked(a, dtype, shape, writable=False):
    if not isinstance(a, np.ndarray) or a.dtype != dtype or a.shape != shape:
        raise ValueError(f"Expected {dtype} array with shape {shape}")
    if not a.flags.c_contiguous or not a.flags.aligned or (writable and not a.flags.writeable):
        raise ValueError("Buffer must be contiguous, aligned, and writable if mutated")
    if not np.isfinite(a).all():
        raise ValueError("Non-finite buffer")
    return a.ctypes.data


class Model:
    def __init__(self, weights=None, seed=42):
        lib = ROOT / "libocr.so"
        if not lib.exists():
            raise RuntimeError("Mojo library missing. Run ./setup.sh first.")
        self.lib = ct.CDLL(str(lib))
        self.lib.ocr_predict.argtypes = [ct.c_size_t] * 4 + [ct.c_ssize_t]
        self.lib.ocr_predict.restype = None
        self.lib.ocr_epoch.argtypes = [ct.c_size_t] * 6 + [ct.c_ssize_t] + [ct.c_float] * 3
        self.lib.ocr_epoch.restype = ct.c_float
        if weights is None:
            rng = np.random.default_rng(seed)
            weights = np.zeros(PARAMS, np.float32)
            weights[:W2] = rng.normal(0, np.sqrt(2 / D), W2)
            weights[W2:B1] = rng.normal(0, np.sqrt(2 / H), C * H)
        self.weights = np.array(weights, dtype=np.float32, order="C", copy=True)
        checked(self.weights, np.float32, (PARAMS,), True)
        self.velocity = np.zeros(PARAMS, np.float32)
        self.metadata = {}

    def predict(self, x):
        x = np.ascontiguousarray(x, dtype=np.float32)
        n = len(x)
        xp = checked(x, np.float32, (n, D))
        wp = checked(self.weights, np.float32, (PARAMS,))
        out = np.empty((n, C), np.float32)
        scratch = np.empty(H, np.float32)
        self.lib.ocr_predict(xp, wp, out.ctypes.data, scratch.ctypes.data, n)
        return out

    def epoch(self, x, y, order, lr=0.003, momentum=0.8, decay=1e-5):
        n = len(x)
        xp = checked(x, np.float32, (n, D))
        yp = checked(y, np.int64, (n,))
        op = checked(order, np.int64, (n,))
        if n == 0 or y.min() < 0 or y.max() >= C or order.min() < 0 or order.max() >= n:
            raise ValueError("Empty dataset or out-of-range labels/indices")
        if not (0 < lr <= 1 and 0 <= momentum < 1 and 0 <= decay <= 1):
            raise ValueError("Invalid optimizer hyperparameters")
        wp = checked(self.weights, np.float32, (PARAMS,), True)
        vp = checked(self.velocity, np.float32, (PARAMS,), True)
        scratch = np.empty(2 * H + C, np.float32)
        return self.lib.ocr_epoch(xp, yp, op, wp, vp, scratch.ctypes.data, n, lr, momentum, decay)

    def save(self, path, **metadata):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        info = (
            self.metadata
            | metadata
            | {"version": VERSION, "alphabet": ALPHABET, "architecture": [D, H, C]}
        )
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("wb") as f:
            np.savez_compressed(f, weights=self.weights, metadata=json.dumps(info))
        temporary.replace(path)

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as data:
            info = json.loads(str(data["metadata"]))
            if (
                info.get("version") != VERSION
                or info.get("alphabet") != ALPHABET
                or info.get("architecture") != [D, H, C]
            ):
                raise ValueError("Incompatible model checkpoint")
            model = cls(data["weights"])
            model.metadata = info
            return model
