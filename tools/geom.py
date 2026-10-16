"""Board geometry shared by gen_pcb.py (layout) and acir.py (link-resistance check).

Two mirrored columns of 7 horizontal 18650 holders at a uniform 27.6 mm pitch.
Every cell-to-cell link is a copper strap with the same resistance: the 12
in-column straps are identical 10 mm x 27.6 mm bars at the holder ends, and the
cell 7 -> cell 8 strap across the centre channel is widened (W_H) so its
resistance matches (tuned with acir.py).
"""
W, H = 297.0, 210.0
MX = W / 2

TOPBAND = 18.0                   # connector band along the top edge
PITCH = 27.6                     # uniform cell pitch
ROWY = [TOPBAND + 11.42 + PITCH * i for i in range(7)]
GAP = 30.0                       # channel between the two columns (holder courtyards)
HOLDER_L = 89.2                  # holder courtyard length
XL = MX - (HOLDER_L + GAP) / 2   # left column centre
XR = MX + (HOLDER_L + GAP) / 2   # right column centre

PAD_X = 39.63                    # holder contact pad centre from holder centre
PAD_W, PAD_H = 7.35, 7.77        # holder contact pad size
STRAP_IN, STRAP_OUT = 37.7, 47.7  # strap x-range from the holder centre (clear of the holder pegs)
FINGER_IN = 19.4                 # finger reaches the alternate THT contact pads
FINGER_HALF = 4.3
W_H = 16.15                      # cell 7 -> cell 8 strap width (equal-resistance, see acir.py)


def cell_row(n):
    return n if n <= 7 else 15 - n


def cell_side(n):
    return "L" if n <= 7 else "R"


def cell_rot(n):
    """holder rotation: pad 2 (-) at -x for rot 0."""
    if n <= 7:
        return 0 if n % 2 else 180
    return 0 if n % 2 == 0 else 180


def cell_xy(n):
    r = cell_row(n)
    return (XL if n <= 7 else XR), ROWY[r - 1]


def end_x(n, which):
    """x sign of the holder end: 'in' = channel side, 'out' = board-edge side."""
    left = n <= 7
    if which == "in":
        return 1 if left else -1
    return -1 if left else 1


def _span(xc, e, a, b):
    x1, x2 = xc + e * a, xc + e * b
    return min(x1, x2), max(x1, x2)


def vstrap_poly(xc, e, r1):
    """C-shaped copper for the link between rows r1 and r1+1 at the holder end e (+1/-1)."""
    y1, y2 = ROWY[r1 - 1], ROWY[r1]
    fa = xc + e * FINGER_IN
    sb = xc + e * STRAP_IN
    sc = xc + e * STRAP_OUT
    h = FINGER_HALF
    return [(fa, y1 - h), (sc, y1 - h), (sc, y2 + h), (fa, y2 + h),
            (fa, y2 - h), (sb, y2 - h), (sb, y1 + h), (fa, y1 + h)]


def hstrap_poly(w_h=None):
    """cell 7 (+) -> cell 8 (-) across the channel at row 7."""
    w_h = W_H if w_h is None else w_h
    y = ROWY[6]
    h, hh = FINGER_HALF, w_h / 2
    la, lp = XL + FINGER_IN, XL + PAD_X
    ra, rp = XR - FINGER_IN, XR - PAD_X
    return [(la, y - h), (lp, y - h), (lp, y - hh), (rp, y - hh), (rp, y - h), (ra, y - h),
            (ra, y + h), (rp, y + h), (rp, y + hh), (lp, y + hh), (lp, y + h), (la, y + h)]


def pad_rect(xc, e, y):
    x = xc + e * PAD_X
    return (x - PAD_W / 2, y - PAD_H / 2, x + PAD_W / 2, y + PAD_H / 2)


def links():
    """the 13 cell-to-cell links: (name, polygon, padA rect, padB rect)."""
    out = []
    # left column: node k joins cell k (+) and cell k+1 (-); rows k, k+1
    for k in range(1, 7):
        e = end_x(k, "in") if k % 2 else end_x(k, "out")
        out.append(("C%d+ -> C%d-" % (k, k + 1), vstrap_poly(XL, e, k),
                    pad_rect(XL, e, ROWY[k - 1]), pad_rect(XL, e, ROWY[k])))
    out.append(("C7+ -> C8-", hstrap_poly(), pad_rect(XL, 1, ROWY[6]), pad_rect(XR, -1, ROWY[6])))
    # right column: node k (8..13) joins cell k (row 15-k) and cell k+1 (row 14-k)
    for k in range(8, 14):
        r_hi = 14 - k
        e = end_x(k, "out") if k % 2 == 0 else end_x(k, "in")
        out.append(("C%d+ -> C%d-" % (k, k + 1), vstrap_poly(XR, e, r_hi),
                    pad_rect(XR, e, ROWY[r_hi - 1]), pad_rect(XR, e, ROWY[r_hi])))
    return out
