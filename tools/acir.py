"""Cell-to-cell interconnect resistance check (2-D finite-difference field solve).

Each link's copper (one layer) is rasterised; the two holder contact pads are held
at 1 V / 0 V and the Laplace equation is solved. Resistance comes out in squares
and is converted to milliohms for 2 oz copper on F.Cu + B.Cu in parallel.

usage: python3 tools/acir.py [--tune]   (needs numpy + scipy)
"""
import os
import sys

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geom  # noqa: E402

H = 0.1                      # grid step, mm
RS_2OZ = 1.72e-8 / 70e-6     # ohm/sq for 70 um copper (25 C)
LAYERS = 2                   # F.Cu + B.Cu


def inside(poly, xs, ys):
    """even-odd point-in-polygon on a grid."""
    X, Y = np.meshgrid(xs, ys)
    res = np.zeros(X.shape, bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cond = (y1 > Y) != (y2 > Y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = (x2 - x1) * (Y - y1) / (y2 - y1) + x1
        res ^= cond & (X < xint)
    return res


def squares(poly, pa, pb):
    xs_all = [p[0] for p in poly]
    ys_all = [p[1] for p in poly]
    xs = np.arange(min(xs_all) - H, max(xs_all) + H, H) + H / 2
    ys = np.arange(min(ys_all) - H, max(ys_all) + H, H) + H / 2
    cu = inside(poly, xs, ys)
    X, Y = np.meshgrid(xs, ys)

    def inrect(r):
        return (X >= r[0]) & (X <= r[2]) & (Y >= r[1]) & (Y <= r[3]) & cu

    a, b = inrect(pa), inrect(pb)
    ny, nx = cu.shape
    idx = -np.ones(cu.shape, int)
    free = cu & ~a & ~b
    idx[free] = np.arange(free.sum())
    n = free.sum()
    rows, cols, vals = [], [], []
    rhs = np.zeros(n)
    fy, fx = np.nonzero(free)
    diag = np.zeros(n)
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        yy, xx = fy + dy, fx + dx
        ok = (yy >= 0) & (yy < ny) & (xx >= 0) & (xx < nx)
        yy, xx, src = yy[ok], xx[ok], idx[fy[ok], fx[ok]]
        nb_cu = cu[yy, xx]
        src, yy, xx = src[nb_cu], yy[nb_cu], xx[nb_cu]
        diag[src] += 1
        nb = idx[yy, xx]
        f = nb >= 0
        rows += list(src[f]); cols += list(nb[f]); vals += [-1.0] * int(f.sum())
        rhs[src[a[yy, xx]]] += 1.0          # Dirichlet 1 V on pad A
    A = sp.csr_matrix((np.r_[vals, diag], (np.r_[rows, np.arange(n)], np.r_[cols, np.arange(n)])), shape=(n, n))
    v = spl.spsolve(A, rhs)
    V = np.zeros(cu.shape)
    V[a] = 1.0
    V[free] = v
    # current leaving pad A (per unit sheet conductance)
    I = 0.0
    ay, ax = np.nonzero(a)
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        yy, xx = ay + dy, ax + dx
        ok = (yy >= 0) & (yy < ny) & (xx >= 0) & (xx < nx)
        yy, xx = yy[ok], xx[ok]
        m = cu[yy, xx] & ~a[yy, xx]
        I += (1.0 - V[yy[m], xx[m]]).sum()
    return 1.0 / I


def report(out=None):
    rows = []
    for name, poly, pa, pb in geom.links():
        sq = squares(poly, pa, pb)
        rows.append((name, sq, sq * RS_2OZ / LAYERS * 1e3))
    sqs = [r[1] for r in rows]
    lines = ["Cell-to-cell interconnect resistance (copper only, F.Cu + B.Cu 2 oz in parallel, 25 C)",
             "%-14s %10s %10s" % ("link", "squares", "mOhm")]
    lines += ["%-14s %10.3f %10.4f" % r for r in rows]
    spread = (max(sqs) - min(sqs)) / (sum(sqs) / len(sqs)) * 100
    lines.append("spread (max-min)/mean = %.2f %%" % spread)
    txt = "\n".join(lines)
    print(txt)
    if out:
        open(out, "w").write(txt + "\n")
    return rows


if __name__ == "__main__":
    if "--tune" in sys.argv:
        name, poly, pa, pb = geom.links()[0]
        target = squares(poly, pa, pb)
        lo, hi = 6.0, 30.0
        for _ in range(18):
            mid = (lo + hi) / 2
            s = squares(geom.hstrap_poly(mid), geom.pad_rect(geom.XL, 1, geom.ROWY[6]),
                        geom.pad_rect(geom.XR, -1, geom.ROWY[6]))
            lo, hi = (mid, hi) if s > target else (lo, mid)
        print("target %.4f sq  ->  W_H = %.3f mm" % (target, (lo + hi) / 2))
    else:
        report(sys.argv[1] if len(sys.argv) > 1 else None)
