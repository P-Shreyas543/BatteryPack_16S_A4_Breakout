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
import geom  # noqa: E402
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


# ================================================================== geometry (see geom.py)
ROWY, XL, XR, LANE = geom.ROWY, geom.XL, geom.XR, 10.4
N = design.node


def mirror(x, side):
    return x if side == "L" else W - x


def upper_lane(r):
    return round(ROWY[r - 1] + LANE, 3)


# series nodes: kind and the y of the inner-layer route that carries them
#   inner = channel end of the holders, outer = board-edge end
NODE = {7: ("in", upper_lane(7))}
for k, r in ((1, 1), (3, 3), (5, 5)):
    NODE[k] = ("in", upper_lane(r))
    NODE[14 - k] = ("in", upper_lane(r))
for k, r in ((2, 2), (4, 4), (6, 6)):
    NODE[k] = ("out", upper_lane(r))
    NODE[14 - k] = ("out", upper_lane(r))

X_TRIAD, X_TP, X_OSV = 31.0, 37.0, 39.6          # left-margin columns (mirrored on the right)
X_IV, X_PTC = 138.0, 140.4                        # channel: inner-node via, PPTC column (left side)
X_BUS0, BUS_P = 143.6, 0.7                        # In1 sense bus inside the channel

# ================================================================== copper: identical cell straps
for i, (name, poly, pa, pb) in enumerate(geom.links()):
    k = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13][i]
    zone(N(k), poly)
# stitching vias, same pattern in every in-column strap
for k in list(range(1, 7)) + list(range(8, 14)):
    if k <= 6:
        xc, r1 = XL, k
        e = geom.end_x(k, "in" if k % 2 else "out")
    else:
        xc, r1 = XR, 14 - k
        e = geom.end_x(k, "out" if k % 2 == 0 else "in")
    for yy in (ROWY[r1 - 1] + 6.5, ROWY[r1] - 6.5):
        for xr in (39.7, 42.7, 45.7):
            via(N(k), xc + e * xr, yy, 0.8, 0.4)
for xx in (XL + geom.PAD_X + 6.5, XR - geom.PAD_X - 6.5):
    for dy in (-4.0, 0.0, 4.0):
        via(N(7), xx, ROWY[6] + dy, 0.8, 0.4)

# pack terminals: B- (cell 1 -) top-left corner, cell 14 (+) top-right corner -> fuse -> PACK+
B_NEG_F = [(21, 1), (127, 1), (127, 9.4), (76, 9.4), (76, 14.5), (56, 14.5), (56, 25.12), (69.5, 25.12),
           (69.5, 33.72), (21, 33.72)]
B_NEG_B = [(21, 1), (76, 1), (76, 14.5), (56, 14.5), (56, 25.12), (69.5, 25.12), (69.5, 33.72), (21, 33.72)]
zone(design.PACK_NEG, B_NEG_F, layers=(F,))
zone(design.PACK_NEG, B_NEG_B, layers=(B,))
zone(design.TOP, [(276, 1), (255, 1), (255, 17.2), (241, 17.2), (241, 25.12), (227.5, 25.12),
                  (227.5, 33.72), (276, 33.72)])
zone(design.PACK_POS, [(170, 1), (250, 1), (250, 14.5), (221, 14.5), (221, 9.4), (170, 9.4)], layers=(F,))
# PACK+ on B.Cu also runs west along the top band to feed the HV indicator / pack TVS
zone(design.PACK_POS, [(93.8, 1), (124.4, 1), (124.4, 10.8), (169.4, 10.8), (169.4, 1), (250, 1),
                       (250, 14.5), (93.8, 14.5)], layers=(B,))

HOLES = [(5, 5), (W - 5, 5), (5, H - 5), (W - 5, H - 5), (12.0, 98.42), (W - 12.0, 98.42)]
for x, y in HOLES:
    keepout(x, y, 3.8)

# ================================================================== cells
for n in range(1, design.NCELLS + 1):
    x, y = geom.cell_xy(n)
    place("BT%d" % n, x, y, geom.cell_rot(n), show_ref=False)

NTC_AT = [("L", 1), ("L", 3), ("L", 5), ("C", 7), ("R", 1), ("R", 3), ("R", 5)]   # gap below row r
Y_NTC_C = 205.6                                     # centre NTC, just below the cell 7 -> 8 strap
NTC_POS = []
for i, (sd, r) in enumerate(NTC_AT):
    xc = {"L": XL, "R": XR, "C": geom.MX}[sd]
    gy = Y_NTC_C if sd == "C" else round((ROWY[r - 1] + ROWY[r]) / 2, 3)
    place("TH%d" % (i + 1), xc - 1.27, gy, 0, show_ref=False)
    NTC_POS.append((sd, xc, gy))


def place_rot(ref, x, y, net_dir):
    """place a 2-pad part vertically so the pad carrying net_dir[0] faces direction net_dir[1] (+1 down)."""
    netn, s = net_dir
    for r in (90, 270):
        fp = place(ref, x, y, r, show_ref=False)
        pp = pads_of(ref)
        pn = [k for k, v in comps[ref]["pins"].items() if v == netn][0]
        if (pp[pn][1] - y) * s > 0:
            return pp
        board.Remove(fp)
    raise RuntimeError(ref)


for n in range(1, design.NCELLS + 1):
    x, y = geom.cell_xy(n)
    side = geom.cell_side(n)
    rot = geom.cell_rot(n)
    sx = lambda v, side=side: mirror(v, side)  # noqa: E731
    pos_inner = (rot == 0) if side == "L" else (rot == 180)
    inner_node = n if pos_inner else n - 1
    outer_node = n - 1 if pos_inner else n
    ly = NODE[inner_node][1]
    s = 1 if ly > y else -1
    xt = sx(X_TRIAD)
    # walk the R / LED / D string outwards from the channel-side node
    chain, cur, left_parts = [], N(inner_node), ["R_REV%d" % n, "LED_REV%d" % n, "D_REV%d" % n]
    while left_parts:
        ref = [r for r in left_parts if cur in comps[r]["pins"].values()][0]
        left_parts.remove(ref)
        chain.append(ref)
        cur = [v for v in comps[ref]["pins"].values() if v != cur][0]
    up_net = N(inner_node)
    prev = None
    for ref, yy in zip(chain, (y + 6.5 * s, y + 1.5 * s, y - 3.5 * s)):
        pp = place_rot(ref, xt, yy, (up_net, s))
        pin_up = [k for k, v in comps[ref]["pins"].items() if v == up_net][0]
        pin_dn = [k for k in pp if k != pin_up][0]
        track(up_net, F, 0.4 if prev is None else 0.3, [(xt, ly) if prev is None else prev, pp[pin_up]])
        prev = pp[pin_dn]
        up_net = comps[ref]["pins"][pin_dn]
    tp_in = ("TP_P%d" if pos_inner else "TP_N%d") % n
    tp_out = ("TP_N%d" if pos_inner else "TP_P%d") % n
    place(tp_in, sx(X_TP), y + 4.0 * s, 0, show_ref=False)
    place(tp_out, sx(X_TP), y - 4.0 * s, 0, show_ref=False)
    # outer node: triad end -> test loop -> finger of the holder contact
    track(N(outer_node), F, 0.4, [prev, pad(tp_out, "1"), (sx(42.2), y - 4.0 * s)])
    # inner node: via of the In1 route -> test loop
    track(N(inner_node), F, 0.4, [(xt, ly), pad(tp_in, "1")])
    via(N(inner_node), xt, ly)
    # silkscreen: polarity marks and a writable cell box
    text("+" if pos_inner else "-", sx(39.5), y + 4.0 * s, 1.1, bold=True)
    text("-" if pos_inner else "+", sx(39.5), y - 4.0 * s, 1.1, bold=True)
    bx0, bx1 = sorted((sx(3.0), sx(20.0)))
    silk_line([(bx0, y - 5.5), (bx1, y - 5.5), (bx1, y + 4.5), (bx0, y + 4.5), (bx0, y - 5.5)], 0.12)
    text("C%d" % n, (bx0 + bx1) / 2, y - 3.0, 1.5, bold=True)
    text("V ______", (bx0 + bx1) / 2, y + 0.2, 0.9)
    text("IR _____", (bx0 + bx1) / 2, y + 2.6, 0.9)

# inner nodes: via at the strap (channel side) and In1 route out to the margin triad
for k, (kind, ly) in NODE.items():
    if kind != "in":
        continue
    for side in (["L", "R"] if k == 7 else ["L" if k < 7 else "R"]):
        xv = mirror(X_IV, side)
        via(N(k), xv, ly, 0.8, 0.4)
        ys = ROWY[6] + geom.W_H / 2 - 0.6 if k == 7 else ly
        track(N(k), F, 0.5, [(xv, ly), (mirror(136.0, side), ys) if k != 7 else (xv, ys)])
        track(N(k), I1, 0.3, [(xv, ly), (mirror(X_TRIAD, side), ly)])
# outer nodes: sense via next to the strap
for k, (kind, ly) in NODE.items():
    if kind == "out":
        side = "L" if k < 7 else "R"
        via(N(k), mirror(X_OSV, side), ly, 0.8, 0.4)
        track(N(k), F, 0.5, [(mirror(X_OSV, side), ly), (mirror(42.2, side), ly)])

# ================================================================== BMS sense: PPTC at every node, bus up the channel
XPIN = [geom.MX - 17.5 + 2.5 * k for k in range(15)]      # J1 pins (top edge, centred)
Y_VIA_J1 = 17.4
Y_FAN = 28.5
place("J1", XPIN[0], 5.5, 0, show_ref=False)


def bus_x(k):
    return geom.MX + BUS_P * (k - 7)          # symmetric about the centre line, tap 7 on it


def bus_up(k, x0, y0):
    """In1 from the PPTC output via to J1 lane k: jog to the bus, up, 45-degree fan, up."""
    xb = bus_x(k)
    d = abs(XPIN[k] - xb)
    track(comps["J1"]["pins"][str(k + 1)], I1, 0.25,
          [(x0, y0), (xb, y0), (xb, Y_FAN), (XPIN[k], Y_FAN - d), (XPIN[k], Y_VIA_J1)])


for k in range(1, 14):
    kind, ly = NODE[k]
    side = "L" if k <= 7 else "R"
    xp = geom.MX if k == 7 else mirror(X_PTC, side)
    f = "F_PTC%d" % (k + 1)
    if k == 7:
        yc = ROWY[6] - geom.W_H / 2 - 3.6
        pp = place_rot(f, xp, yc, (N(7), +1))
        p1 = [v for q, v in pp.items() if comps[f]["pins"][q] == N(7)][0]
        p2 = [v for q, v in pp.items() if comps[f]["pins"][q] != N(7)][0]
        track(N(7), F, 0.5, [p1, (xp, ROWY[6] - geom.W_H / 2 + 0.6)])
        yo = yc - 4.0
    elif kind == "in":
        yc = ly + 3.2
        pp = place_rot(f, xp, yc, (N(k), -1))
        p1 = [v for q, v in pp.items() if comps[f]["pins"][q] == N(k)][0]
        p2 = [v for q, v in pp.items() if comps[f]["pins"][q] != N(k)][0]
        track(N(k), F, 0.4, [(mirror(X_IV, side), ly), p1])
        yo = yc + 4.0
    else:
        yc = ly - 3.4
        pp = place_rot(f, xp, yc, (N(k), +1))
        p1 = [v for q, v in pp.items() if comps[f]["pins"][q] == N(k)][0]
        p2 = [v for q, v in pp.items() if comps[f]["pins"][q] != N(k)][0]
        via(N(k), xp, ly)
        track(N(k), F, 0.4, [(xp, ly), p1])
        track(N(k), I1, 0.25, [(mirror(X_OSV, side), ly), (xp, ly)])
        yo = yc - 4.0
    bms = comps[f]["pins"]["2"] if comps[f]["pins"]["1"] == N(k) else comps[f]["pins"]["1"]
    track(bms, F, 0.4, [p2, (xp, yo)])
    via(bms, xp, yo)
    bus_up(k, xp, yo)

# B- and cell 14 taps: PPTC in the corner copper (outer margin), In1 lane along y = row1 - 10.4
Y_TAPLANE = round(ROWY[0] - LANE, 3)
for k, side in ((0, "L"), (14, "R")):
    f = "F_PTC%d" % (k + 1)
    pp = place_rot(f, mirror(26.0, side), 22.0, (N(k), +1))           # tap pad down, output up
    p2 = [v for q, v in pp.items() if comps[f]["pins"][q] != N(k)][0]
    bms = comps["J1"]["pins"][str(k + 1)]
    vx, vy = mirror(26.0, side), 17.6
    track(bms, F, 0.4, [p2, (vx, vy)])
    via(bms, vx, vy)
    track(bms, I1, 0.25, [(vx, vy), (vx, Y_TAPLANE), (XPIN[k], Y_TAPLANE), (XPIN[k], Y_VIA_J1)])

# J1 lanes: pin -> two staggered rows of SOD-323 TVS -> via
Y_TVS_A, Y_TVS_B = 12.6, 15.0
for k in range(1, 15):
    t = "D_TVS%d" % k
    m = min(k, 15 - k)                       # k and 15-k are mirror partners
    if m == 7:                               # centre pair: vertical, pad on lane 7 at the top
        xc = XPIN[7] + (-1.1 if k == 7 else 1.1)
        yc = (Y_TVS_A + Y_TVS_B) / 2
        pp = place_rot(t, xc, yc, (comps["J1"]["pins"]["8"], -1))
        for q, v in pp.items():
            lane = [j for j in range(15) if comps["J1"]["pins"][str(j + 1)] == comps[t]["pins"][q]][0]
            track(comps[t]["pins"][q], F, 0.3, [v, (XPIN[lane], v[1])])
    else:
        place(t, XPIN[k - 1] + 1.25, Y_TVS_B if (7 - m) % 2 == 1 else Y_TVS_A, 0, show_ref=False)
for k in range(15):
    bms = comps["J1"]["pins"][str(k + 1)]
    track(bms, F, 0.3, [pad("J1", str(k + 1)), (XPIN[k], Y_VIA_J1)])
    via(bms, XPIN[k], Y_VIA_J1)

# ================================================================== NTC: J2 right of J1, lines on In2
XJ2 = 173.0
place("J2", XJ2, 5.5, 0, show_ref=False)
LG = 1.3
for i, (sd, xc, gy) in enumerate(NTC_POS):
    th = "TH%d" % (i + 1)
    a, b = pad(th, "1"), pad(th, "2")
    na, nb = comps[th]["pins"]["1"], comps[th]["pins"]["2"]
    if sd == "C":
        # centre NTC: straight up the middle of the channel, then to J2 pins 7/8
        for pt, nt, xl, yl, pn in ((a, na, geom.MX - 0.65, 14.3, "7"), (b, nb, geom.MX + 0.65, 15.0, "8")):
            pj = pad("J2", pn)
            track(nt, I2, 0.25, [pt, (pt[0], gy - 1.4), (xl, gy - 2.0), (xl, yl), (pj[0], yl), pj])
        continue
    for pt, nt, dy, j in ((a, na, -LG, 0), (b, nb, LG, 1)):
        if sd == "L":
            w = 2 * i + j
            xt, yt = 91.6 + 0.7 * w, 9.9 + 0.7 * w
        else:
            w = 2 * (i - 4) + j
            xt, yt = 211.0 + 0.7 * w, 13.4 - 0.7 * w
            w += 8
        pj = pad("J2", str(w + 1))
        track(nt, I2, 0.25, [pt, (pt[0], gy + dy), (xt, gy + dy), (xt, yt), (pj[0], yt), pj])

# ================================================================== power path, top right
place("J4", 67.0, 9.0, 0)                 # B- / PACK- lug
place("J3", W - 67.0, 9.0, 0)             # PACK+ lug
place("F1", 251.0, 9.5, 180)              # pad1 (cell 14) east, pad2 (PACK+) west
pl = None
for r in (0, 180):
    fp = place("LED_FB1", 250.4, 2.4, r, show_ref=False)
    pp = pads_of("LED_FB1")
    if pp["1"][0] < 250.4:                # cathode (PACK+) west
        pl = pp
        break
    board.Remove(fp)
for r in (0, 180):
    fp = place("R_FB1", 254.4, 2.4, r, show_ref=False)
    pr = pads_of("R_FB1")
    ptop = [v for q, v in pr.items() if comps["R_FB1"]["pins"][q] == design.TOP][0]
    if ptop[0] > 254.4:
        break
    board.Remove(fp)
pmid = [v for q, v in pr.items() if comps["R_FB1"]["pins"][q] != design.TOP][0]
track(comps["LED_FB1"]["pins"]["2"], F, 0.3, [pl["2"], pmid])
track(design.TOP, F, 0.4, [ptop, (256.0, ptop[1])])

# HV-present indicator + pack TVS: top band, inside the PACK- copper, PACK+ through vias to B.Cu
YH = 5.0
place("D_HV1", 95.2, YH, 270, show_ref=False)          # K south, A north-east
place("R_HV_BASE1", 99.3, 4.06, 0, show_ref=False)
place("R_HV_PD1", 99.3, 7.2, 270, show_ref=False)
place("Q_HV1", 103.8, YH, 0, show_ref=False)
place("LED_HV1", 107.8, YH, 0, show_ref=False)
place("R_HV_LED1", 112.1, YH, 180, show_ref=False)
place("D_TVS_MAIN1", 119.4, YH, 0, show_ref=False)
c = comps
track(c["D_HV1"]["pins"]["1"], F, 0.3, [pad("D_HV1", "1"), pad("R_HV_BASE1", "1")])
hb = c["Q_HV1"]["pins"]["1"]
track(hb, F, 0.3, [pad("R_HV_BASE1", "2"), pad("Q_HV1", "1")])
ppd = [v for q, v in pads_of("R_HV_PD1").items() if c["R_HV_PD1"]["pins"][q] == hb][0]
track(hb, F, 0.3, [ppd, pad("R_HV_BASE1", "2")])
track(c["Q_HV1"]["pins"]["3"], F, 0.3, [pad("Q_HV1", "3"), pad("LED_HV1", "1")])
pla = [v for q, v in pads_of("R_HV_LED1").items() if c["R_HV_LED1"]["pins"][q] != design.PACK_POS][0]
plp = [v for q, v in pads_of("R_HV_LED1").items() if c["R_HV_LED1"]["pins"][q] == design.PACK_POS][0]
track(c["LED_HV1"]["pins"]["2"], F, 0.3, [pad("LED_HV1", "2"), pla])
for pt in (pad("D_HV1", "3"), plp):
    track(design.PACK_POS, F, 0.4, [pt, (pt[0], 8.0)])
    via(design.PACK_POS, pt[0], 8.0)
ptv = [v for q, v in pads_of("D_TVS_MAIN1").items() if c["D_TVS_MAIN1"]["pins"][q] == design.PACK_POS][0]
for dx in (-0.9, 0.9):
    track(design.PACK_POS, F, 0.6, [ptv, (ptv[0] + dx, 8.6)])
    via(design.PACK_POS, ptv[0] + dx, 8.6, 0.8, 0.4)

# ================================================================== mechanical
for i, (x, y) in enumerate(HOLES):
    place("H%d" % (i + 1), x, y, 0, show_ref=False)
for i, (x, y) in enumerate([(14.0, 3.4), (W - 14.0, 3.4), (14.0, H - 3.4), (W - 14.0, H - 3.4)]):
    place("FID%d" % (i + 1), x, y, 0, show_ref=False)

# ================================================================== silkscreen
text("J1  BMS BALANCE   1 = B-  ...  15 = C14+", geom.MX, 20.2, 0.9)
text("J2  BMS NTC  (7 sensors)", W - 102.0, 12.6, 1.2, bold=True)
text("pins 2n-1 / 2n = NTCn   |   NTC4 = centre bus", W - 102.0, 14.9, 0.8)
text("B- / PACK-", 67.0, 15.0, 1.3, bold=True)
text("to BMS B-", 67.0, 17.0, 0.9)
text("PACK+", W - 67.0, 15.2, 1.3, bold=True)
text("to load / charger +", W - 67.0, 17.2, 0.9)
text("F1  5x20  10A", 251.0, 15.6, 0.9)
text("FUSE BLOWN", 252.4, 0.9, 0.8)
text("HV>44V", 107.8, 1.2, 0.8)
text("14S 18650 BATTERY PACK BREAKOUT", 102.0, 12.6, 1.2, bold=True)
text("58.8V MAX  |  A4  |  4-LAYER  |  EQUAL 0.26 mOhm CELL LINKS", 102.0, 14.9, 0.8)
for i, (sd, xc, gy) in enumerate(NTC_POS):
    a, b = design.NTC_CELLS[i]
    if sd == "C":
        text("NTC%d BUS" % (i + 1), xc + 5.5, gy, 0.8, just=-1)
    else:
        text("NTC%d  C%d/C%d" % (i + 1, a, b), xc + 9.0, gy, 0.8)
guide = ["HOW TO CONNECT",
         "1. J1 <- BMS balance lead (B- wire = pin 1)",
         "2. J2 <- BMS NTC lead (optional)",
         "3. B- lug -> BMS B-  |  PACK+ lug -> load +",
         "4. Load / charger -  -> BMS P-",
         "5. Insert cells LAST. Red LED = reversed cell"]
for i, g in enumerate(guide):
    text(g, geom.MX - 4.25 + 1.7 * i, 112.0, 0.9, bold=(i == 0), rot=90)
text("CELL 7 (+)  ->  CELL 8 (-)", geom.MX, ROWY[6] + 4.0, 1.0)
text("WARNING: LIVE 58.8V DC - INSERT CELLS WITH CORRECT POLARITY - RED LED = REVERSED CELL", geom.MX, 208.7, 0.8)

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
# board.Save() rewrites the project files with API defaults - keep the user's settings
_keepfiles = {p: open(p).read() for p in (PCB[:-10] + ".kicad_pro", PCB[:-10] + ".kicad_prl") if os.path.exists(p)}
board.Save(PCB)
for p, txt in _keepfiles.items():
    open(p, "w").write(txt)
print("board written:", len(board.GetFootprints()), "footprints,", len(board.GetTracks()), "tracks/vias")
