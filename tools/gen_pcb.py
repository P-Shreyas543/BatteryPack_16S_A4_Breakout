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
XL, XR = 66.8, W - 66.8
YL = [17.5, 43.8, 67.1, 93.4, 116.7, 143.0, 166.3, 192.6]          # BT1..BT8  (left, top->bottom)
YR = {9: 192.6, 10: 166.3, 11: 143.0, 12: 116.7, 13: 93.4, 14: 67.1}  # BT9..BT14 (right, bottom->top)
LANE = 10.4  # inner-layer lane offset from holder centre (clear of holder pads and pegs)


def cell_xy(n):
    if n <= 8:
        return XL, YL[n - 1], (180 if n % 2 else 0), "L"
    return XR, YR[n], (0 if n % 2 else 180), "R"


def gap(y1, y2):
    return round((y1 + y2) / 2, 3)


# series-node geometry: side ("L"/"R"), inner/outer, y of the route that carries it
#   inner node -> via at the channel edge; outer node -> via in the outer margin
NODE = {}
NODE[0] = ("L", "in", YL[0] - LANE)
NODE[1] = ("L", "out", YL[0] + LANE)
NODE[2] = ("L", "in", gap(YL[1], YL[2]))
NODE[3] = ("L", "out", YL[2] + LANE)
NODE[4] = ("L", "in", gap(YL[3], YL[4]))
NODE[5] = ("L", "out", YL[4] + LANE)
NODE[6] = ("L", "in", gap(YL[5], YL[6]))
NODE[7] = ("L", "out", YL[6] + LANE)
NODE[8] = ("LR", "in", YL[7] + LANE)
NODE[9] = ("R", "out", YR[10] + LANE)
NODE[10] = ("R", "in", gap(YR[10], YR[11]))
NODE[11] = ("R", "out", YR[12] + LANE)
NODE[12] = ("R", "in", gap(YR[12], YR[13]))
NODE[13] = ("R", "out", YR[14] + LANE)
NODE[14] = ("R", "in", YR[14] - LANE)

X_INV_L, X_INV_R = 112.6, W - 112.6      # inner-node vias (channel edge)
X_OUTSENSE_L, X_OUTSENSE_R = 18.0, W - 18.0  # outer-node sense vias
X_TRIAD_L, X_TRIAD_R = 11.0, W - 11.0      # triad column / inner-route via
X_TP_L, X_TP_R = 4.6, W - 4.6

# ================================================================== zones (F.Cu + B.Cu)
ZL_OUT = (1.0, 48.0)
ZL_IN = (85.7, 114.5)
ZR_OUT = (W - 48.0, W - 1.0)
ZR_IN = (W - 114.5, W - 85.7)
N = design.node
zone(N(1), rect(ZL_OUT[0], YL[0] - 5, ZL_OUT[1], YL[1] + 5))
zone(N(3), rect(ZL_OUT[0], YL[2] - 5, ZL_OUT[1], YL[3] + 5))
zone(N(5), rect(ZL_OUT[0], YL[4] - 5, ZL_OUT[1], YL[5] + 5))
zone(N(7), rect(ZL_OUT[0], YL[6] - 5, ZL_OUT[1], YL[7] + 5))
zone(N(2), rect(ZL_IN[0], YL[1] - 5, ZL_IN[1], YL[2] + 5))
zone(N(4), rect(ZL_IN[0], YL[3] - 5, ZL_IN[1], YL[4] + 5))
zone(N(6), rect(ZL_IN[0], YL[5] - 5, ZL_IN[1], YL[6] + 5))
zone(N(9), rect(ZR_OUT[0], YR[10] - 5, ZR_OUT[1], YR[9] + 5))
zone(N(11), rect(ZR_OUT[0], YR[12] - 5, ZR_OUT[1], YR[11] + 5))
zone(N(13), rect(ZR_OUT[0], YR[14] - 5, ZR_OUT[1], YR[13] + 5))
zone(N(10), rect(ZR_IN[0], YR[11] - 5, ZR_IN[1], YR[10] + 5))
zone(N(12), rect(ZR_IN[0], YR[13] - 5, ZR_IN[1], YR[12] + 5))
# bottom bus: cell 8 (+) -> cell 9 (-)
zone(N(8), rect(ZL_IN[0], YL[7] - 6, ZR_IN[1], 205.5))
# PACK- strip across the top: cell 1 (-) -> J4 / TVS / HV indicator
zone(design.PACK_NEG, rect(ZL_IN[0], 3.0, W - 1.0, 24.0))
# cell 14 (+) up to the fuse
zone(design.TOP, [(183.0, 33.0), (205.0, 33.0), (205.0, 56.0), (ZR_IN[1], 56.0), (ZR_IN[1], 72.5), (183.0, 72.5)])
# PACK+ after the fuse
zone(design.PACK_POS, rect(214.0, 29.0, W - 1.0, 52.0))

HOLES = [(5, 5), (W - 5, 5), (5, H - 5), (W - 5, H - 5), (MX, 7), (MX, H - 7)]
for x, y in HOLES:
    keepout(x, y, 3.8)

# ================================================================== cells
for n in range(1, design.NCELLS + 1):
    x, y, rot, side = cell_xy(n)
    place("BT%d" % n, x, y, rot, show_ref=False)

# NTC saddles: left column top->bottom, then right column top->bottom
NTC_POS = [(XL, gap(YL[0], YL[1])), (XL, gap(YL[2], YL[3])), (XL, gap(YL[4], YL[5])), (XL, gap(YL[6], YL[7])),
           (XR, gap(YR[14], YR[13])), (XR, gap(YR[12], YR[11])), (XR, gap(YR[10], YR[9]))]
for i, (x, y) in enumerate(NTC_POS):
    place("TH%d" % (i + 1), x - 1.27, y, 0, show_ref=False)

# per-cell outer-margin group: triad, test loops, route via for the cell's inner node
for n in range(1, design.NCELLS + 1):
    x, y, rot, side = cell_xy(n)
    left = side == "L"
    sx = (lambda v: v) if left else (lambda v: W - v)
    pos_inner = (rot == 0) if left else (rot == 180)  # + terminal on the channel side?
    inner_node = n if pos_inner else n - 1
    outer_node = n - 1 if pos_inner else n
    ly = NODE[inner_node][2]
    s = 1 if ly > y else -1
    xt = sx(X_TRIAD_L)
    # triad order from the inner node outwards
    chain = ["D_REV%d" % n, "LED_REV%d" % n, "R_REV%d" % n]  # + ... -
    if not pos_inner:
        chain.reverse()
    ys = [y + 6.0 * s, y + 1.0 * s, y - 4.0 * s]
    inner_net = N(inner_node)
    up_net = inner_net  # net that must face the inner via (towards s)
    prev_bottom = None
    for ref, yy in zip(chain, ys):
        c = comps[ref]["pins"]
        # rotation so that the pad carrying `up_net` faces the via side
        best = None
        for r in (90, 270):
            fp = place(ref, xt, yy, r, show_ref=False)
            pp = pads_of(ref)
            pn = [k for k, v in c.items() if v == up_net][0]
            ok = (pp[pn][1] - yy) * s > 0
            if ok:
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
    # last pad belongs to the outer node -> tie into the outer zone with a short stub
    track(N(outer_node), F, 0.4, [prev_bottom, (prev_bottom[0], prev_bottom[1] - 2.0 * s)])
    # test loops: inner-node loop next to the via, outer-node loop sits in the outer zone
    tp_in = ("TP_P%d" if pos_inner else "TP_N%d") % n
    tp_out = ("TP_N%d" if pos_inner else "TP_P%d") % n
    place(tp_in, sx(X_TP_L), y + 6.5 * s, 0, show_ref=False)
    place(tp_out, sx(X_TP_L), y - 4.5 * s, 0, show_ref=False)
    track(inner_net, F, 0.4, [(xt, ly), pad(tp_in, "1")])
    via(inner_net, xt, ly)
    # silkscreen
    lx = sx(X_TP_L + 3.4)
    text("C%d" % n, sx(X_TRIAD_L + 6.3), y, 1.5, bold=True)
    text("+", lx, (y + 6.5 * s) if pos_inner else (y - 4.5 * s), 1.2, bold=True)
    text("-", lx, (y - 4.5 * s) if pos_inner else (y + 6.5 * s), 1.2, bold=True)

# ================================================================== inner-layer routes from nodes
# triad/test-loop routes: inner node via at the channel edge -> In1 lane -> outer margin via
for k, (side, kind, ly) in NODE.items():
    if kind != "in":
        continue
    sides = ["L", "R"] if side == "LR" else [side]
    for sd in sides:
        if (sd == "L" and k > 8) or (sd == "R" and k < 8):
            continue
        xi = X_INV_L if sd == "L" else X_INV_R
        xt = X_TRIAD_L if sd == "L" else X_TRIAD_R
        if k in (0, 14) or sd in ("L", "R"):
            track(N(k), I1, 0.3, [(xi, ly), (xt, ly)])
        via(N(k), xi, ly, 0.8, 0.4)

# outer-node sense routes: via in the outer zone -> In1 lane -> channel
for k, (side, kind, ly) in NODE.items():
    if kind != "out":
        continue
    xo = X_OUTSENSE_L if side == "L" else X_OUTSENSE_R
    via(N(k), xo, ly, 0.8, 0.4)

# ================================================================== BMS sense block (channel)
Y0 = 77.0
ROW = [Y0 + 4.0 * k for k in range(design.NCELLS + 1)]
XA, XB = 127.0, 134.0          # PPTC columns (even / odd rows)
XT1, XT2 = 141.0, 146.0        # TVS columns (odd / even k)
XJ1 = 160.0
YJ1 = Y0 + 10.5
for k in range(design.NCELLS + 1):
    xc = XA if k % 2 == 0 else XB
    place("F_PTC%d" % (k + 1), xc, ROW[k], 0, show_ref=False)
for k in range(1, design.NCELLS + 1):
    xc = XT1 if k % 2 else XT2
    place("D_TVS%d" % k, xc, (ROW[k - 1] + ROW[k]) / 2, 270, show_ref=False)
place("J1", XJ1, YJ1, 270, show_ref=False)
XS = 148.6  # fan-out start

for k in range(design.NCELLS + 1):
    bms = comps["J1"]["pins"][str(k + 1)]
    f = "F_PTC%d" % (k + 1)
    p1, p2 = pad(f, "1"), pad(f, "2")
    vin = (p1[0] - 1.6, ROW[k])
    via(N(k), *vin)
    track(N(k), F, 0.4, [vin, p1])
    yj = YJ1 + 2.5 * k
    d = yj - ROW[k]
    track(bms, F, 0.4, [p2, (XS, ROW[k]), (XS + abs(d), yj), pad("J1", str(k + 1))])

# left nodes 0..8 -> rows 0..8 ; above group (entry above row) and below group
ENTRY_L = {k: NODE[k][2] for k in range(0, 9)}
TRUNK_L = {0: 116.6, 1: 115.95, 2: 115.3, 3: 114.65,             # above: top entry nearest block
           4: 114.0, 5: 114.65, 6: 115.3, 7: 115.95, 8: 116.6}    # below: bottom entry nearest block
for k in range(0, 9):
    ye, xt = ENTRY_L[k], TRUNK_L[k]
    x0 = X_INV_L if NODE[k][1] == "in" else X_OUTSENSE_L
    vin = (pad("F_PTC%d" % (k + 1), "1")[0] - 1.6, ROW[k])
    track(N(k), I1, 0.25, [(x0, ye), (xt, ye), (xt, ROW[k]), vin])

# right nodes 9..14 wrap under the block and come up the west side
X_E = {14: 176.0, 13: 176.65, 12: 177.3, 11: 177.95, 9: 178.6, 10: 179.25}
Y_B = {14: 137.0, 13: 137.65, 12: 138.3, 11: 138.95, 10: 139.6, 9: 140.25}
X_W = {14: 121.0, 13: 120.35, 12: 119.7, 11: 119.05, 10: 118.4, 9: 117.75}
for k in range(9, 15):
    ye = NODE[k][2]
    x0 = X_INV_R if NODE[k][1] == "in" else X_OUTSENSE_R
    vin = (pad("F_PTC%d" % (k + 1), "1")[0] - 1.6, ROW[k])
    track(N(k), I1, 0.25, [(x0, ye), (X_E[k], ye), (X_E[k], Y_B[k]), (X_W[k], Y_B[k]), (X_W[k], ROW[k]), vin])

# ================================================================== NTC routes (In2) -> J2
XJ2, YJ2 = 150.0, 150.0
place("J2", XJ2, YJ2, 270, show_ref=False)
LG = 1.3  # lane offset inside the holder gap
for i, (x, y) in enumerate(NTC_POS):
    th = "TH%d" % (i + 1)
    a, b = pad(th, "1"), pad(th, "2")
    na, nb = comps[th]["pins"]["1"], comps[th]["pins"]["2"]
    pa, pb = pad("J2", str(2 * i + 1)), pad("J2", str(2 * i + 2))
    if i < 4:   # left column -> west face of J2
        xa_t = {0: 121.0, 1: 119.7, 2: 118.4}.get(i, 120.35)
        xb_t = {0: 120.35, 1: 119.05, 2: 117.75}.get(i, 121.0)
        track(na, I2, 0.25, [a, (a[0], y - LG), (xa_t, y - LG), (xa_t, pa[1]), pa])
        track(nb, I2, 0.25, [b, (b[0], y + LG), (xb_t, y + LG), (xb_t, pb[1]), pb])
    else:       # right column -> east face of J2
        j = i - 4
        xa_t = 166.0 + 1.3 * j
        xb_t = 166.65 + 1.3 * j
        track(na, I2, 0.25, [a, (a[0], y - LG), (xa_t, y - LG), (xa_t, pa[1]), pa])
        track(nb, I2, 0.25, [b, (b[0], y + LG), (xb_t, y + LG), (xb_t, pb[1]), pb])

# ================================================================== power path (top right)
place("F1", 208.3, 40.0, 0)
place("J3", 275.0, 41.0, 0)
place("J4", 275.0, 13.5, 0)
place("D_TVS_MAIN1", 252.0, 26.5, 270)
# fuse-blown indicator under the fuse
place("R_FB1", 208.5, 49.5, 0, show_ref=False)
place("LED_FB1", 212.3, 49.5, 180, show_ref=False)
track(design.TOP, F, 0.4, [pad("R_FB1", "1"), (204.0, 49.5)])
track(comps["R_FB1"]["pins"]["2"], F, 0.3, [pad("R_FB1", "2"), pad("LED_FB1", "2")])
track(design.PACK_POS, F, 0.4, [pad("LED_FB1", "1"), (215.0, 49.5)])

# HV-present indicator in the channel, under the PACK- strip
YH = 37.05
place("D_HV1", 134.0, YH - 0.95, 180, show_ref=False)      # K (pad 3) west, A (pad 1) east
place("R_HV_BASE1", 139.5, YH, 0, show_ref=False)
place("R_HV_PD1", 144.0, 38.0, 270, show_ref=False)          # pad1 (base) top, pad2 (PACK-) bottom
place("Q_HV1", 147.0, 38.0, 0, show_ref=False)               # B top-left, E bottom-left, C right
place("LED_HV1", 152.0, 38.0, 0, show_ref=False)
place("R_HV_LED1", 157.0, 38.0, 180, show_ref=False)
pp = pad
hz, hb = comps["D_HV1"]["pins"]["1"], comps["Q_HV1"]["pins"]["1"]
hk, ha = comps["Q_HV1"]["pins"]["3"], comps["R_HV_LED1"]["pins"]["2"]
track(hz, F, 0.3, [pp("D_HV1", "1"), pp("R_HV_BASE1", "1")])
track(hb, F, 0.3, [pp("R_HV_BASE1", "2"), (142.5, pp("R_HV_BASE1", "2")[1]), pp("R_HV_PD1", "1")])
track(hb, F, 0.3, [pp("R_HV_PD1", "1"), pp("Q_HV1", "1")])
track(design.PACK_NEG, F, 0.3, [pp("R_HV_PD1", "2"), pp("Q_HV1", "2")])
track(design.PACK_NEG, F, 0.4, [pp("R_HV_PD1", "2"), (pp("R_HV_PD1", "2")[0], 41.0)])
via(design.PACK_NEG, pp("R_HV_PD1", "2")[0], 41.0)
track(design.PACK_NEG, I1, 0.3, [(pp("R_HV_PD1", "2")[0], 41.0), (pp("R_HV_PD1", "2")[0], 20.0)])
via(design.PACK_NEG, pp("R_HV_PD1", "2")[0], 20.0)
track(hk, F, 0.3, [pp("Q_HV1", "3"), pp("LED_HV1", "1")])
track(ha, F, 0.3, [pp("LED_HV1", "2"), pp("R_HV_LED1", "2")])
# PACK+ feed from the PACK+ zone along y=30.5
k3, r1 = pp("D_HV1", "3"), pp("R_HV_LED1", "1")
track(design.PACK_POS, F, 0.4, [(216.0, 30.5), (r1[0], 30.5), (131.5, 30.5), (131.5, k3[1]), k3])
track(design.PACK_POS, F, 0.4, [(r1[0], 30.5), r1])

# ================================================================== mechanical
for i, (x, y) in enumerate(HOLES):
    place("H%d" % (i + 1), x, y, 0, show_ref=False)
for i, (x, y) in enumerate([(15.0, 3.6), (W - 14.0, 3.6), (15.0, H - 3.6)]):
    place("FID%d" % (i + 1), x, y, 0, show_ref=False)

# ================================================================== silkscreen
text("14S 18650 BATTERY PACK BREAKOUT", MX, 26.2, 1.5, bold=True)
text("58.8V MAX  |  A4 297 x 210 mm  |  4-LAYER", MX, 28.6, 1.0)
text("BMS CELL SENSE  J1  (JST XH 15P)", XJ1 - 1.0, Y0 - 4.6, 1.0)
for k in range(design.NCELLS + 1):
    text("B-" if k == 0 else "C%d" % k, XJ1 + 4.5, YJ1 + 2.5 * k, 0.9, just=-1)
text("NTC  J2  (JST XH 14P)", XJ2, YJ2 - 5.0, 1.0)
for i in range(design.NNTC):
    text("T%d" % (i + 1), XJ2 + 4.5, YJ2 + 5.0 * i + 1.25, 0.9, just=-1)
for i, (x, y) in enumerate(NTC_POS):
    text("NTC%d" % (i + 1), x + 6.5, y, 0.9)
text("PACK+", 275.0, 48.5, 1.4, bold=True)
text("PACK-", 275.0, 21.0, 1.4, bold=True)
text("F1  5x20mm  10A", 208.3, 34.0, 1.0)
text("HV >44V", 152.0, 34.6, 1.0)
text("FUSE BLOWN", 210.4, 52.2, 0.9)
text("CELL 8 (+)  -->  CELL 9 (-)   BUS", MX, 192.0, 1.2)
text("WARNING: LIVE 58.8V DC. INSERT CELLS WITH CORRECT POLARITY - RED LED = REVERSED CELL.", MX, 208.0, 1.0)

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
# board.Save() rewrites the project files with API defaults - keep the user's settings
_keepfiles = {p: open(p).read() for p in (PCB[:-10] + ".kicad_pro", PCB[:-10] + ".kicad_prl") if os.path.exists(p)}
board.Save(PCB)
for p, txt in _keepfiles.items():
    open(p, "w").write(txt)
print("board written:", len(board.GetFootprints()), "footprints,", len(board.GetTracks()), "tracks/vias")
