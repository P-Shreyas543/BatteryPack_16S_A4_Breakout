"""Build the 14S A4 board from the schematic netlist (run with KiCad 10 python).

usage: python3 tools/gen_pcb.py <project dir> <netlist.net>

Keeps the existing stack-up / design settings and the A4 (297 x 210 mm) Edge.Cuts,
replaces every footprint, track, via, zone and silkscreen item.
"""
import os
import sys

import pcbnew
from pcbnew import FromMM, VECTOR2I

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design  # noqa: E402
import sexpr  # noqa: E402
from sexpr import find, find1  # noqa: E402

PRJ, NETFILE = sys.argv[1], sys.argv[2]
PCB = os.path.join(PRJ, design.PROJECT + ".kicad_pcb")
SYSFP = "/usr/share/kicad/footprints"

F, B, I1, I2 = pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu
W, H = 297.0, 210.0
MX = W / 2  # mirror axis


def V(x, y):
    return VECTOR2I(FromMM(x), FromMM(y))


def mm(v):
    return (round(pcbnew.ToMM(v.x), 4), round(pcbnew.ToMM(v.y), 4))


# ------------------------------------------------------------------ clean board
_src = sexpr.parse(open(PCB).read())
_keep = []
for it in _src:
    if isinstance(it, list) and it and it[0] in ("footprint", "segment", "via", "arc", "zone", "group",
                                                  "gr_text", "gr_text_box", "dimension", "target", "net",
                                                  "generated", "image", "table"):
        continue
    if isinstance(it, list) and it and str(it[0]).startswith("gr_"):
        ly = find1(it, "layer")
        if not (ly and ly[1] == "Edge.Cuts"):
            continue
    _keep.append(it)
_tmp = PCB.replace(".kicad_pcb", "_tmp.kicad_pcb")
open(_tmp, "w").write(sexpr.dump(_keep) + "\n")
board = pcbnew.LoadBoard(_tmp)
os.remove(_tmp)

# ------------------------------------------------------------------ netlist
nl = sexpr.parse(open(NETFILE).read())
comps = {}
for c in find(find1(nl, "components"), "comp"):
    ref = find1(c, "ref")[1]
    fields = {}
    for f in find(find1(c, "fields"), "field"):
        name = find1(f, "name")[1]
        atoms = [x for x in f[1:] if not isinstance(x, list)]
        val = atoms[0] if atoms else ""
        fields[name] = val
    props = {find1(p, "name")[1]: (find1(p, "value") or [0, ""])[1] for p in find(c, "property")}
    sp = find1(c, "sheetpath")
    comps[ref] = dict(value=find1(c, "value")[1], fp=find1(c, "footprint")[1], fields=fields, props=props,
                      path=find1(sp, "tstamps")[1] + find1(c, "tstamps")[1], pins={})
for n in find(find1(nl, "nets"), "net"):
    name = find1(n, "name")[1]
    ni = pcbnew.NETINFO_ITEM(board, name)
    board.Add(ni)
    for x in find(n, "node"):
        comps[find1(x, "ref")[1]]["pins"][find1(x, "pin")[1]] = name

NET = {}


def net(name):
    if name not in NET:
        NET[name] = board.FindNet(name)
        assert NET[name] is not None, name
    return NET[name]


def netname(short):
    """resolve a design-level net name to the netlist name (local labels get a sheet prefix)."""
    for n in board.GetNetsByName().keys():
        s = str(n)
        if s == short or s.endswith("/" + short):
            return s
    raise KeyError(short)


# ------------------------------------------------------------------ footprints
FPS = {}


def place(ref, x, y, rot=0, show_ref=True):
    c = comps[ref]
    lib, name = c["fp"].split(":")
    libdir = os.path.join(PRJ, "footprints.pretty") if lib == "footprints" else os.path.join(SYSFP, lib + ".pretty")
    fp = pcbnew.FootprintLoad(libdir, name)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    board.Add(fp)
    fp.SetReference(ref)
    fp.SetValue(c["value"])
    for k in ("LCSC", "MPN", "Manufacturer", "Description"):
        v = c["fields"].get(k, "")
        if v:
            fp.SetField(k, v)
            fld = fp.GetField(k)
            if fld is not None:
                fld.SetVisible(False)
                fld.SetLayer(pcbnew.F_Fab)
    fp.SetPath(pcbnew.KIID_PATH(c["path"]))
    fp.SetSheetname(c["props"].get("Sheetname", ""))
    fp.SetSheetfile(c["props"].get("Sheetfile", ""))
    fp.SetPosition(V(x, y))
    fp.SetOrientationDegrees(rot)
    for p in fp.Pads():
        n = c["pins"].get(p.GetNumber())
        if n:
            p.SetNet(net(n))
    fp.Reference().SetVisible(show_ref)
    fp.Reference().SetTextSize(V(1.0, 1.0))
    fp.Reference().SetTextThickness(FromMM(0.15))
    FPS[ref] = fp
    return fp


def pad(ref, num):
    """position of the first pad with this number."""
    for p in FPS[ref].Pads():
        if p.GetNumber() == num:
            return mm(p.GetPosition())
    raise KeyError((ref, num))


def pads_of(ref):
    return {p.GetNumber(): mm(p.GetPosition()) for p in FPS[ref].Pads() if p.GetNumber()}


def track(netn, layer, width, pts):
    for a, b in zip(pts, pts[1:]):
        if a == b:
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(V(*a))
        t.SetEnd(V(*b))
        t.SetWidth(FromMM(width))
        t.SetLayer(layer)
        t.SetNet(net(netn))
        board.Add(t)


_vias = set()


def via(netn, x, y, d=0.6, drill=0.3):
    key = (round(x, 3), round(y, 3))
    if key in _vias:
        return
    _vias.add(key)
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(V(x, y))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(F, B)
    v.SetWidth(F, FromMM(d))
    v.SetDrill(FromMM(drill))
    v.SetNet(net(netn))
    board.Add(v)


def zone(netn, poly, layers=(F, B), clearance=0.6, prio=0):
    for ly in layers:
        z = pcbnew.ZONE(board)
        z.SetLayer(ly)
        z.SetNet(net(netn))
        ol = z.Outline()
        ol.NewOutline()
        for x, y in poly:
            ol.Append(FromMM(x), FromMM(y))
        z.SetLocalClearance(FromMM(clearance))
        z.SetMinThickness(FromMM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetAssignedPriority(prio)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        board.Add(z)


def keepout(x, y, r):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetLayerSet(pcbnew.LSET.AllCuMask())
    z.SetDoNotAllowZoneFills(True)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    ol = z.Outline()
    ol.NewOutline()
    import math
    for i in range(24):
        a = 2 * math.pi * i / 24
        ol.Append(FromMM(x + r * math.cos(a)), FromMM(y + r * math.sin(a)))
    board.Add(z)


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def text(s, x, y, size=1.2, layer=pcbnew.F_SilkS, bold=False, rot=0, just=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(V(x, y))
    t.SetLayer(layer)
    t.SetTextSize(V(size, size))
    t.SetTextThickness(FromMM(size * (0.2 if bold else 0.15)))
    t.SetTextAngleDegrees(rot)
    if just < 0:
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    elif just > 0:
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    board.Add(t)


def silk_line(pts, w=0.15, layer=pcbnew.F_SilkS):
    for a, b in zip(pts, pts[1:]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(*a))
        s.SetEnd(V(*b))
        s.SetLayer(layer)
        s.SetWidth(FromMM(w))
        board.Add(s)


# ================================================================== geometry
# Two mirrored columns of 7 cells.  Series path: left column top->bottom (cells 1..7),
# bus along the bottom of the channel, right column bottom->top (cells 8..14).
# With 7 cells per column, B- (cell 1 -) lands at the top-left corner and cell 14 +
# at the top-right corner, so every external connection sits on the top edge.
XL, XR = 66.8, W - 66.8
ROWY = [40.8, 67.1, 90.4, 116.7, 140.0, 166.3, 192.6]   # row 1..7 holder centres
LANE = 10.4   # inner-layer lane offset from a holder centre (clear of holder pads/pegs)


def cell_row(n):
    return n if n <= 7 else 15 - n


def cell_xy(n):
    r = cell_row(n)
    if n <= 7:
        return XL, ROWY[r - 1], (0 if n % 2 else 180), "L"
    return XR, ROWY[r - 1], (0 if n % 2 == 0 else 180), "R"


def gap(r1, r2):
    return round((ROWY[r1 - 1] + ROWY[r2 - 1]) / 2, 3)


def lane_below(r):
    return round(ROWY[r - 1] + LANE, 3)


def side_of(k):
    return "L" if k <= 7 else "R"


# series node k: (kind, route y).  inner = channel side, outer = board-edge side
NODE = {
    0: ("top", None), 14: ("top", None),
    1: ("in", lane_below(1)), 13: ("in", lane_below(1)),
    2: ("out", gap(2, 3)), 12: ("out", gap(2, 3)),
    3: ("in", lane_below(3)), 11: ("in", lane_below(3)),
    4: ("out", gap(4, 5)), 10: ("out", gap(4, 5)),
    5: ("in", lane_below(5)), 9: ("in", lane_below(5)),
    6: ("out", lane_below(6)), 8: ("out", lane_below(6)),
    7: ("in", lane_below(7)),
}
X_INV_L, X_INV_R = 112.6, W - 112.6
X_OUTSENSE_L, X_OUTSENSE_R = 18.0, W - 18.0
X_TRIAD_L, X_TRIAD_R = 11.0, W - 11.0
X_TP_L = 4.6
N = design.node

# ================================================================== zones (F.Cu + B.Cu)
ZL_OUT = (1.0, 48.0)
ZL_IN = (85.7, 114.5)
ZR_OUT = (W - 48.0, W - 1.0)
ZR_IN = (W - 114.5, W - 85.7)


def rows_rect(xr, r1, r2):
    return rect(xr[0], ROWY[r1 - 1] - 5, xr[1], ROWY[r2 - 1] + 5)


for (k, xr, r1, r2) in [(2, ZL_OUT, 2, 3), (4, ZL_OUT, 4, 5), (6, ZL_OUT, 6, 7),
                        (1, ZL_IN, 1, 2), (3, ZL_IN, 3, 4), (5, ZL_IN, 5, 6),
                        (12, ZR_OUT, 2, 3), (10, ZR_OUT, 4, 5), (8, ZR_OUT, 6, 7),
                        (13, ZR_IN, 1, 2), (11, ZR_IN, 3, 4), (9, ZR_IN, 5, 6)]:
    zone(N(k), rows_rect(xr, r1, r2))
zone(N(7), rect(ZL_IN[0], ROWY[6] - 5, ZR_IN[1], 205.5))                     # bottom bus 7 -> 8
YTB = 29.0  # bottom of the top connector band
# PACK- : cell 1 (-) at the top-left corner + left half of the top band
zone(design.PACK_NEG, [(1, 1), (119, 1), (119, YTB), (48, YTB), (48, ROWY[0] + 5.7), (1, ROWY[0] + 5.7)])
zone(design.PACK_NEG, rect(100, 22.5, 212, 29.6), layers=(B,), prio=1)                # return strip for TVS/HV
# cell 14 (+) at the top-right corner up to the fuse
zone(design.TOP, [(230, 1), (W - 1, 1), (W - 1, ROWY[0] + 5.7), (249, ROWY[0] + 5.7), (249, YTB), (230, YTB)])
# PACK+ after the fuse
zone(design.PACK_POS, rect(178, 1, 226, YTB), layers=(F,))
zone(design.PACK_POS, rect(178, 1, 226, 21.9), layers=(B,))

HOLES = [(5, 5), (W - 5, 5), (5, H - 5), (W - 5, H - 5), (127.0, 115.0), (W - 127.0, 115.0)]
for x, y in HOLES:
    keepout(x, y, 3.8)

# ================================================================== cells
for n in range(1, design.NCELLS + 1):
    x, y, rot, side = cell_xy(n)
    place("BT%d" % n, x, y, rot, show_ref=False)

# NTC saddles, numbered along the series path: left column down, right column up
NTC_ROWS = [("L", 1, 2), ("L", 3, 4), ("L", 5, 6), ("L", 6, 7), ("R", 5, 6), ("R", 3, 4), ("R", 1, 2)]
NTC_POS = []
for i, (sd, r1, r2) in enumerate(NTC_ROWS):
    y = gap(r1, r2)
    if sd == "L":
        place("TH%d" % (i + 1), XL - 1.27, y, 0, show_ref=False)      # pad1 west
    else:
        place("TH%d" % (i + 1), XR + 1.27, y, 180, show_ref=False)    # pad1 east
    NTC_POS.append((sd, XL if sd == "L" else XR, y))


def inner_route_y(n, inner_node):
    if inner_node == 0 or inner_node == 14:
        return None
    return NODE[inner_node][1]


for n in range(1, design.NCELLS + 1):
    x, y, rot, side = cell_xy(n)
    left = side == "L"
    sx = (lambda v: v) if left else (lambda v: W - v)
    pos_inner = (rot == 0) if left else (rot == 180)   # + terminal on the channel side?
    inner_node = n if pos_inner else n - 1
    outer_node = n - 1 if pos_inner else n
    ly = NODE[inner_node][1]
    s = 1 if ly > y else -1
    xt = sx(X_TRIAD_L)
    chain = ["D_REV%d" % n, "LED_REV%d" % n, "R_REV%d" % n]   # + ... -
    if not pos_inner:
        chain.reverse()
    ys = [y + 6.0 * s, y + 1.0 * s, y - 4.0 * s]
    inner_net = N(inner_node)
    up_net = inner_net
    prev_bottom = None
    for ref, yy in zip(chain, ys):
        c = comps[ref]["pins"]
        best = None
        for r in (90, 270):
            fp = place(ref, xt, yy, r, show_ref=False)
            pp = pads_of(ref)
            pn = [k for k, v in c.items() if v == up_net][0]
            if (pp[pn][1] - yy) * s > 0:
                best = r
                break
            board.Remove(fp)
        assert best is not None, ref
        pp = pads_of(ref)
        pin_up = [k for k, v in c.items() if v == up_net][0]
        pin_dn = [k for k in pp if k != pin_up][0]
        if prev_bottom is None:
            track(inner_net, F, 0.4, [(xt, ly), pp[pin_up]])
        else:
            track(up_net, F, 0.3, [prev_bottom, pp[pin_up]])
        prev_bottom = pp[pin_dn]
        up_net = c[pin_dn]
    track(N(outer_node), F, 0.4, [prev_bottom, (prev_bottom[0], prev_bottom[1] - 2.0 * s)])
    tp_in = ("TP_P%d" if pos_inner else "TP_N%d") % n
    tp_out = ("TP_N%d" if pos_inner else "TP_P%d") % n
    place(tp_in, sx(X_TP_L), y + 6.5 * s, 0, show_ref=False)
    place(tp_out, sx(X_TP_L), y - 4.5 * s, 0, show_ref=False)
    track(inner_net, F, 0.4, [(xt, ly), pad(tp_in, "1")])
    via(inner_net, xt, ly)
    lx = sx(X_TP_L + 3.4)
    text("C%d" % n, sx(X_TRIAD_L + 6.3), y, 1.5, bold=True)
    text("+", lx, (y + 6.5 * s) if pos_inner else (y - 4.5 * s), 1.2, bold=True)
    text("-", lx, (y - 4.5 * s) if pos_inner else (y + 6.5 * s), 1.2, bold=True)

# inner nodes: via at the channel edge, In1 lane out to the outer-margin triad via
for k, (kind, ly) in NODE.items():
    if kind != "in":
        continue
    sides = ["L", "R"] if k == 7 else [side_of(k)]
    for sd in sides:
        xi = X_INV_L if sd == "L" else X_INV_R
        xt = X_TRIAD_L if sd == "L" else X_TRIAD_R
        track(N(k), I1, 0.3, [(xi, ly), (xt, ly)])
        via(N(k), xi, ly, 0.8, 0.4)
# outer nodes: sense via in the outer zone
for k, (kind, ly) in NODE.items():
    if kind == "out":
        via(N(k), X_OUTSENSE_L if k <= 7 else X_OUTSENSE_R, ly, 0.8, 0.4)

# ================================================================== top edge: connectors
XJ1, YJ = 131.0, 5.5           # J1 pin 1 (balance, 15 pins, B- at the left)
XJ2 = 38.0                     # J2 pin 1 (NTC, 14 pins)
place("J1", XJ1, YJ, 0, show_ref=False)
place("J2", XJ2, YJ, 0, show_ref=False)
place("J4", MX - 44.5, 13.0, 0)       # PACK- / B- lug
place("J3", MX + 44.5, 13.0, 0)       # PACK+ lug
place("F1", 226.7, 24.0, 180)         # pad1 (cell 14) east, pad2 (PACK+) west

# ================================================================== BMS sense block under J1
XK = [MX - 28.0 + 4.0 * k for k in range(design.NCELLS + 1)]   # 4 mm lanes
Y_TVS = {0: 24.0, 1: 30.0}     # TVS rows (even k / odd k)
Y_PTC = {1: 38.0, 0: 45.0}     # PPTC rows (odd k / even k)
Y_IN = {1: 41.9, 0: 48.9}      # input vias (odd / even)
for k in range(1, design.NCELLS + 1):
    place("D_TVS%d" % k, (XK[k - 1] + XK[k]) / 2, Y_TVS[k % 2], 0, show_ref=False)
for k in range(design.NCELLS + 1):
    place("F_PTC%d" % (k + 1), XK[k], Y_PTC[k % 2], 90, show_ref=False)
for k in range(design.NCELLS + 1):
    bms = comps["J1"]["pins"][str(k + 1)]
    f = "F_PTC%d" % (k + 1)
    pj = pad("J1", str(k + 1))
    d = abs(pj[0] - XK[k])
    track(bms, F, 0.4, [pj, (pj[0], 8.0), (XK[k], 8.0 + d), pad(f, "2")])
    p1 = pad(f, "1")
    vin = (XK[k], Y_IN[k % 2])
    track(N(k), F, 0.4, [p1, vin])
    via(N(k), *vin)

# In1 sense routes: every entry runs horizontally to its lane, then straight up to the input via
for k in range(1, 14):
    kind, ye = NODE[k]
    if k == 7:
        ye = 195.0
        via(N(7), X_INV_L, ye, 0.8, 0.4)
        x0 = X_INV_L
    elif kind == "in":
        x0 = X_INV_L if k <= 7 else X_INV_R
    else:
        x0 = X_OUTSENSE_L if k <= 7 else X_OUTSENSE_R
    track(N(k), I1, 0.25, [(x0, ye), (XK[k], ye), (XK[k], Y_IN[k % 2])])
# B- and cell 14 come from the top corners
via(design.PACK_NEG, 117.0, 25.0, 0.8, 0.4)
track(design.PACK_NEG, I1, 0.25, [(117.0, 25.0), (117.0, 50.5), (XK[0], 50.5), (XK[0], Y_IN[0])])
via(design.TOP, 245.0, 27.0, 0.8, 0.4)
track(design.TOP, I1, 0.25, [(245.0, 27.0), (245.0, 30.2), (181.0, 30.2), (181.0, 50.5),
                             (XK[14], 50.5), (XK[14], Y_IN[0])])

# ================================================================== NTC routes (In2) -> J2 (top-left)
LG = 1.3
for i, (sd, x, y) in enumerate(NTC_POS):
    th = "TH%d" % (i + 1)
    a, b = pad(th, "1"), pad(th, "2")
    na, nb = comps[th]["pins"]["1"], comps[th]["pins"]["2"]
    pa, pb = pad("J2", str(2 * i + 1)), pad("J2", str(2 * i + 2))
    if sd == "L":
        wa, wb = 2 * i, 2 * i + 1
        for pt, nt, w, pj, dy in ((a, na, wa, pa, -LG), (b, nb, wb, pb, LG)):
            xt, yt = 71.0 + 0.6 * w, 27.0 - 0.6 * w
            track(nt, I2, 0.25, [pt, (pt[0], y + dy), (xt, y + dy), (xt, yt), (pj[0], yt), pj])
    else:
        j = i - 4
        for pt, nt, r, pj, dy in ((a, na, 2 * j, pa, LG), (b, nb, 2 * j + 1, pb, -LG)):
            xt, yt = 221.0 + 0.6 * r, 21.5 - 0.6 * r
            track(nt, I2, 0.25, [pt, (pt[0], y + dy), (xt, y + dy), (xt, yt), (pj[0], yt), pj])

# ================================================================== power path extras (top right)
# fuse-blown indicator bridging the PACK+ zone (west) and the cell-14 zone (east)
def place_facing(ref, x, y, net_east):
    for r in (0, 180):
        fp = place(ref, x, y, r, show_ref=False)
        pp = pads_of(ref)
        pe = [k for k, v in comps[ref]["pins"].items() if v == net_east][0]
        if pp[pe][0] > x:
            return pp
        board.Remove(fp)
    raise RuntimeError(ref)


fb_mid = comps["R_FB1"]["pins"]["2"] if comps["R_FB1"]["pins"]["1"] == design.TOP else comps["R_FB1"]["pins"]["1"]
pl = place_facing("LED_FB1", 225.9, 10.0, fb_mid)
pr = place_facing("R_FB1", 229.9, 10.0, design.TOP)
la = [v for k, v in pl.items() if comps["LED_FB1"]["pins"][k] == fb_mid][0]
rm = [v for k, v in pr.items() if comps["R_FB1"]["pins"][k] == fb_mid][0]
track(fb_mid, F, 0.3, [la, rm])
# pack TVS: PACK+ zone on top, PACK- through vias into the B.Cu return strip
place("D_TVS_MAIN1", 210.3, 17.0, 90, show_ref=False)
pt1 = [v for k, v in pads_of("D_TVS_MAIN1").items() if comps["D_TVS_MAIN1"]["pins"][k] == design.PACK_NEG][0]
for dx in (-1.0, 0.0, 1.0):
    via(design.PACK_NEG, pt1[0] + dx, 24.2, 0.8, 0.4)
    track(design.PACK_NEG, F, 0.5, [pt1, (pt1[0] + dx, 24.2)])
# HV-present indicator (PACK+ zone supplies the zener and LED resistor directly)
YH = 25.05
place("D_HV1", 181.0, YH - 0.95, 180, show_ref=False)
place("R_HV_BASE1", 186.5, YH, 0, show_ref=False)
place("R_HV_PD1", 191.0, 26.0, 270, show_ref=False)
place("Q_HV1", 194.0, 26.0, 0, show_ref=False)
place("LED_HV1", 199.0, 26.0, 0, show_ref=False)
place("R_HV_LED1", 204.0, 26.0, 180, show_ref=False)
hz, hb = comps["D_HV1"]["pins"]["1"], comps["Q_HV1"]["pins"]["1"]
hk, ha = comps["Q_HV1"]["pins"]["3"], comps["R_HV_LED1"]["pins"]["2"]
track(hz, F, 0.3, [pad("D_HV1", "1"), pad("R_HV_BASE1", "1")])
track(hb, F, 0.3, [pad("R_HV_BASE1", "2"), (189.5, pad("R_HV_BASE1", "2")[1]), pad("R_HV_PD1", "1")])
track(hb, F, 0.3, [pad("R_HV_PD1", "1"), pad("Q_HV1", "1")])
track(design.PACK_NEG, F, 0.3, [pad("R_HV_PD1", "2"), pad("Q_HV1", "2")])
track(design.PACK_NEG, F, 0.4, [pad("R_HV_PD1", "2"), (pad("R_HV_PD1", "2")[0], 28.9)])
via(design.PACK_NEG, pad("R_HV_PD1", "2")[0], 28.9)
track(hk, F, 0.3, [pad("Q_HV1", "3"), pad("LED_HV1", "1")])
track(ha, F, 0.3, [pad("LED_HV1", "2"), pad("R_HV_LED1", "2")])

# ================================================================== mechanical
for i, (x, y) in enumerate(HOLES):
    place("H%d" % (i + 1), x, y, 0, show_ref=False)
for i, (x, y) in enumerate([(16.0, 3.4), (W - 14.0, 3.4), (16.0, H - 3.4)]):
    place("FID%d" % (i + 1), x, y, 0, show_ref=False)

# ================================================================== silkscreen
text("J1  BALANCE  ->  BMS   (1 = B-  ...  15 = C14+)", XJ1 + 17.5, 11.2, 1.0)
text("J2  NTC  ->  BMS   (1-2 = NTC1 ... 13-14 = NTC7)", XJ2 + 16.25, 11.2, 1.0)
text("B-  /  PACK-", MX - 44.5, 19.6, 1.3, bold=True)
text("to BMS B-", MX - 44.5, 21.8, 1.0)
text("PACK+", MX + 44.5, 19.6, 1.3, bold=True)
text("to load / charger +", MX + 44.5, 21.8, 1.0)
text("F1 5x20 10A", 226.7, 17.4, 1.0)
text("HV>44V", 199.0, 23.6, 0.8)
text("FUSE BLOWN", 227.9, 7.6, 0.8)
for i, (sd, x, y) in enumerate(NTC_POS):
    text("NTC%d" % (i + 1), x + (6.5 if sd == "L" else -6.5), y, 0.9)
YT = 58.0
text("14S 18650 BATTERY PACK BREAKOUT", MX, YT, 1.5, bold=True)
text("58.8V MAX  |  A4 297 x 210 mm  |  4-LAYER", MX, YT + 2.6, 1.0)
guide = ["HOW TO CONNECT",
         "1. J1 <- BMS balance lead (B- wire on pin 1)",
         "2. J2 <- BMS NTC lead (or leave open)",
         "3. B- lug -> BMS B-     PACK+ lug -> load/charger +",
         "4. Load/charger - -> BMS P-",
         "5. Insert cells LAST. A red LED = that cell is reversed.",
         "Test loops: red = cell +, black = cell -"]
for i, g in enumerate(guide):
    text(g, MX, YT + 8.0 + 2.2 * i, 1.0, bold=(i == 0))
text("CELL 7 (+)  -->  CELL 8 (-)   BUS", MX, 199.0, 1.2)
text("WARNING: LIVE 58.8V DC. INSERT CELLS WITH CORRECT POLARITY - RED LED = REVERSED CELL.", MX, 208.0, 1.0)

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
# board.Save() rewrites the project files with API defaults - keep the user's settings
_keepfiles = {p: open(p).read() for p in (PCB[:-10] + ".kicad_pro", PCB[:-10] + ".kicad_prl") if os.path.exists(p)}
board.Save(PCB)
for p, txt in _keepfiles.items():
    open(p, "w").write(txt)
print("board written:", len(board.GetFootprints()), "footprints,", len(board.GetTracks()), "tracks/vias")
