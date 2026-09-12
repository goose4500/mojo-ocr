"""Float32 MLP: SIMD forward, softmax, cross-entropy, backprop, momentum SGD.

Private C ABI: native.py validates NumPy-owned buffers before passing addresses.
The caller owns all memory. No Python/NumPy math runs inside these kernels.
"""
from std.memory import MutPointer
from std.math import exp, log

comptime FPtr = MutPointer[Float32, MutAnyOrigin]
comptime IPtr = MutPointer[Int64, MutAnyOrigin]
comptime D = 768
comptime H = 128
comptime C = 94
comptime W2 = H * D
comptime B1 = W2 + C * H
comptime B2 = B1 + H

@always_inline
def dot(a: FPtr, b: FPtr, n: Int) -> Float32:
    var acc = SIMD[DType.float32, 8](0)
    for i in range(0, n, 8):
        acc += a.unsafe_load[width=8](i) * b.unsafe_load[width=8](i)
    return acc.reduce_add()

@always_inline
def forward(x: FPtr, w: FPtr, h: FPtr, p: FPtr):
    for j in range(H):
        h[unsafe_offset=j] = max(Float32(0), dot(x, w.unsafe_offset(j * D), D) + w[unsafe_offset=B1 + j])
    var peak = Float32(-1e30)
    for k in range(C):
        p[unsafe_offset=k] = dot(h, w.unsafe_offset(W2 + k * H), H) + w[unsafe_offset=B2 + k]
        peak = max(peak, p[unsafe_offset=k])
    var total = Float32(0)
    for k in range(C):
        p[unsafe_offset=k] = exp(p[unsafe_offset=k] - peak)
        total += p[unsafe_offset=k]
    for k in range(C):
        p[unsafe_offset=k] /= total

@export
def ocr_predict(x_addr: Int, w_addr: Int, out_addr: Int, scratch_addr: Int, n: Int) abi("C"):
    var x = FPtr(unsafe_from_address=x_addr)
    var w = FPtr(unsafe_from_address=w_addr)
    var outp = FPtr(unsafe_from_address=out_addr)
    var h = FPtr(unsafe_from_address=scratch_addr)
    for i in range(n):
        forward(x.unsafe_offset(i * D), w, h, outp.unsafe_offset(i * C))

@export
def ocr_epoch(x_addr: Int, y_addr: Int, order_addr: Int, w_addr: Int, v_addr: Int, scratch_addr: Int, n: Int, lr: Float32, momentum: Float32, decay: Float32) abi("C") -> Float32:
    var x = FPtr(unsafe_from_address=x_addr)
    var y = IPtr(unsafe_from_address=y_addr)
    var order = IPtr(unsafe_from_address=order_addr)
    var w = FPtr(unsafe_from_address=w_addr)
    var v = FPtr(unsafe_from_address=v_addr)
    var h = FPtr(unsafe_from_address=scratch_addr)
    var p = h.unsafe_offset(H)
    var dh = p.unsafe_offset(C)
    var loss = Float32(0)
    for sample in range(n):
        var idx = Int(order[unsafe_offset=sample])
        var row = x.unsafe_offset(idx * D)
        forward(row, w, h, p)
        var label = Int(y[unsafe_offset=idx])
        loss -= log(max(p[unsafe_offset=label], Float32(1e-12)))
        p[unsafe_offset=label] -= 1
        for j in range(H):
            dh[unsafe_offset=j] = 0
        # Compute hidden derivatives BEFORE updating the output weights.
        for k in range(C):
            var delta = p[unsafe_offset=k]
            for j in range(0, H, 8):
                var wp = w.unsafe_offset(W2 + k * H + j)
                var vp = v.unsafe_offset(W2 + k * H + j)
                dh.unsafe_offset(j).unsafe_store(dh.unsafe_load[width=8](j) + wp.unsafe_load[width=8]() * delta)
                var grad = h.unsafe_load[width=8](j) * delta + wp.unsafe_load[width=8]() * decay
                var velocity = vp.unsafe_load[width=8]() * momentum + grad
                vp.unsafe_store(velocity)
                wp.unsafe_store(wp.unsafe_load[width=8]() - velocity * lr)
            v[unsafe_offset=B2 + k] = momentum * v[unsafe_offset=B2 + k] + delta
            w[unsafe_offset=B2 + k] -= lr * v[unsafe_offset=B2 + k]
        for j in range(H):
            var delta = dh[unsafe_offset=j] if h[unsafe_offset=j] > 0 else Float32(0)
            for i in range(0, D, 8):
                var wp = w.unsafe_offset(j * D + i)
                var vp = v.unsafe_offset(j * D + i)
                var grad = row.unsafe_load[width=8](i) * delta + wp.unsafe_load[width=8]() * decay
                var velocity = vp.unsafe_load[width=8]() * momentum + grad
                vp.unsafe_store(velocity)
                wp.unsafe_store(wp.unsafe_load[width=8]() - velocity * lr)
            v[unsafe_offset=B1 + j] = momentum * v[unsafe_offset=B1 + j] + delta
            w[unsafe_offset=B1 + j] -= lr * v[unsafe_offset=B1 + j]
    return loss / Float32(max(n, 1))
