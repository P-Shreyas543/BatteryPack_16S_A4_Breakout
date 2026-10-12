"""Generate the hierarchical KiCad 10 schematic from design.py.

usage: python3 tools/gen_sch.py <kicad symbol dir> <project dir>
"""
import copy
import math
import os
import sys
import uuid

import design
import sexpr
from sexpr import Sym, find, find1

SYMDIR, OUT = sys.argv[1], sys.argv[2]
NS = uuid.UUID("6b1f2c7e-14a5-4c3e-9a51-0b5e14d00014")
ROOT_UUID = "00000000-0000-0000-0000-000000000001"
SHEET_UUID = ["00000000-0000-0000-0000-00000000000%d" % (i + 2) for i in range(5)]
DATE = "2026-10-12"
REV = "Rev 2.0 (14S)"
COMPANY = "Battery Pack Breakout - 14S / A4"


def uid(*k):
    return str(uuid.uuid5(NS, "/".join(map(str, k))))


# ------------------------------------------------------------------ library
_libs = {}


def lib(name):
    if name not in _libs:
        _libs[name] = {s[1]: s for s in find(sexpr.parse(open(os.path.join(SYMDIR, name + ".kicad_sym")).read()), "symbol")}
    return _libs[name]


def lib_symbol(lib_id):
    lname, sname = lib_id.split(":")
    s = copy.deepcopy(lib(lname)[sname])
    ext = find1(s, "extends")
    if ext:
        parent = copy.deepcopy(lib(lname)[ext[1]])
        props = find(s, "property")
        body = [x for x in parent if not (isinstance(x, list) and x[0] == "property")]
        # keep parent's flags, swap in child properties, rename units
        out = [Sym("symbol"), sname]
        for x in body[2:]:
            if isinstance(x, list) and x[0] == "symbol":
                x[1] = x[1].replace(ext[1], sname, 1)
            out.append(x)
        # properties must come before sub-symbols
        first_sub = next(i for i, x in enumerate(out) if isinstance(x, list) and x[0] == "symbol")
        s = out[:first_sub] + props + out[first_sub:]
    s[1] = lib_id
    return s


def pins_of(libsym):
    """pin number -> (x, y, angle) in library coordinates (y up)."""
    res = {}
    for sub in find(libsym, "symbol"):
        parts = sub[1].rsplit("_", 2)
        if parts[-2] not in ("0", "1") or parts[-1] not in ("0", "1"):
            continue
        for p in find(sub, "pin"):
            at = find1(p, "at")
            res[find1(p, "number")[1]] = (float(at[1]), float(at[2]), float(at[3]))
    return res


# ------------------------------------------------------------------ sheet builder
def eff(size=1.27, justify=None, hide=False, bold=False):
    font = [Sym("font"), [Sym("size"), size, size]]
    if bold:
        font.append([Sym("bold"), Sym("yes")])
    e = [Sym("effects"), font]
    if justify:
        e.append([Sym("justify")] + [Sym(j) for j in justify.split()])
    return e


def prop(name, value, x, y, ang=0, hide=False, size=1.27, justify=None):
    p = [Sym("property"), name, value, [Sym("at"), x, y, ang]]
    if hide:
        p.append([Sym("hide"), Sym("yes")])
    p += [[Sym("show_name"), Sym("no")], [Sym("do_not_autoplace"), Sym("no")], eff(size, justify)]
    return p


DIRS = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}  # screen unit vectors


class Sheet:
    def __init__(self, idx, name, title):
        self.idx, self.name, self.title = idx, name, title
        self.uuid = ROOT_UUID if idx is None else SHEET_UUID[idx]
        self.items, self.libids = [], []
        self.pinpos = {}

    def path(self):
        return "/" + ROOT_UUID if self.idx is None else "/%s/%s" % (ROOT_UUID, self.uuid)

    def place(self, part, x, y, rot=0, ref_off=(3.0, -1.5), val_off=(3.0, 1.5)):
        ls = lib_symbol(part["sym"])
        if part["sym"] not in self.libids:
            self.libids.append(part["sym"])
        su = uid("sym", part["ref"])
        part["uuid"] = su
        part["sheet_uuid"] = self.uuid
        s = [Sym("symbol"), [Sym("lib_id"), part["sym"]], [Sym("at"), x, y, rot], [Sym("unit"), 1],
             [Sym("body_style"), 1], [Sym("exclude_from_sim"), Sym("no")],
             [Sym("in_bom"), Sym("yes" if part["lcsc"] else "no")],
             [Sym("on_board"), Sym("yes")], [Sym("in_pos_files"), Sym("yes")], [Sym("dnp"), Sym("no")],
             [Sym("uuid"), su]]
        fa = (360 - rot) % 360
        s.append(prop("Reference", part["ref"], x + ref_off[0], y + ref_off[1], fa, justify="left"))
        s.append(prop("Value", part["value"], x + val_off[0], y + val_off[1], fa, size=1.0, justify="left"))
        s.append(prop("Footprint", part["fp"], x, y, 0, hide=True))
        s.append(prop("Datasheet", "", x, y, 0, hide=True))
        s.append(prop("Description", part["desc"], x, y, 0, hide=True))
        for k, v in (("LCSC", part["lcsc"]), ("MPN", part["mpn"]), ("Manufacturer", part["mfr"])):
            if v:
                s.append(prop(k, v, x, y, 0, hide=True))
        pins = pins_of(ls)
        for num in sorted(pins, key=lambda n: (len(n), n)):
            s.append([Sym("pin"), num, [Sym("uuid"), uid("pin", part["ref"], num)]])
        s.append([Sym("instances"), [Sym("project"), design.PROJECT,
                  [Sym("path"), self.path(), [Sym("reference"), part["ref"]], [Sym("unit"), 1]]]])
        self.items.append(s)
        # absolute pin positions and outward direction
        r = math.radians(rot)
        for num, (px, py, pa) in pins.items():
            xr = px * math.cos(r) - py * math.sin(r)
            yr = px * math.sin(r) + py * math.cos(r)
            out = int(round(pa + 180 + rot)) % 360
            self.pinpos[(part["ref"], num)] = (round(x + xr, 3), round(y - yr, 3), out)
        return pins

    def pin(self, ref, num):
        return self.pinpos[(ref, num)]

    def wire(self, a, b):
        self.items.append([Sym("wire"), [Sym("pts"), [Sym("xy"), a[0], a[1]], [Sym("xy"), b[0], b[1]]],
                           [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]],
                           [Sym("uuid"), uid("w", self.name, len(self.items))]])

    def connect(self, p1, p2):
        (x1, y1), (x2, y2) = p1[:2], p2[:2]
        if x1 == x2 or y1 == y2:
            self.wire((x1, y1), (x2, y2))
        else:
            self.wire((x1, y1), (x1, y2))
            self.wire((x1, y2), (x2, y2))

    def label(self, ref, num, net, stub=2.54, glob=None):
        x, y, d = self.pin(ref, num)
        dx, dy = DIRS[d]
        ex, ey = round(x + dx * stub, 3), round(y + dy * stub, 3)
        self.wire((x, y), (ex, ey))
        self.net_label(net, ex, ey, d, glob)

    def net_label(self, net, x, y, d, glob=None):
        if glob is None:
            glob = net in design.GLOBAL_NETS
        just = {0: "left", 180: "right", 90: "left", 270: "right"}[d]
        u = uid("l", self.name, net, x, y)
        if glob:
            self.items.append([Sym("global_label"), net, [Sym("shape"), Sym("bidirectional")],
                               [Sym("at"), x, y, d], [Sym("fields_autoplaced"), Sym("yes")],
                               eff(1.27, just), [Sym("uuid"), u],
                               prop("Intersheetrefs", "${INTERSHEET_REFS}", x, y, 0, hide=True)])
        else:
            self.items.append([Sym("label"), net, [Sym("at"), x, y, d], eff(1.27, just + " bottom"),
                               [Sym("uuid"), u]])

    def text(self, s, x, y, size=1.27, bold=False):
        self.items.append([Sym("text"), s, [Sym("exclude_from_sim"), Sym("no")], [Sym("at"), x, y, 0],
                           eff(size, "left top", bold=bold), [Sym("uuid"), uid("t", self.name, s[:40], x, y)]])

    def dump(self, extra=()):
        tb = [Sym("title_block"), [Sym("title"), self.title], [Sym("date"), DATE], [Sym("rev"), REV],
              [Sym("company"), COMPANY],
              [Sym("comment"), 1, "14S Li-ion 18650 (58.8V max / 50.4V nom) | IEC 62368-1 ES2 hazard >60V not reached"],
              [Sym("comment"), 2, "All parts JLCPCB/LCSC sourced - LCSC field on every symbol"]]
        doc = [Sym("kicad_sch"), [Sym("version"), 20260306], [Sym("generator"), "eeschema"],
               [Sym("generator_version"), "10.0"], [Sym("uuid"), self.uuid], [Sym("paper"), "A3"], tb,
               [Sym("lib_symbols")] + [lib_symbol(l) for l in self.libids]]
        doc += self.items
        doc += list(extra)
        doc.append([Sym("embedded_fonts"), Sym("no")])
        return sexpr.dump(doc) + "\n"


# ------------------------------------------------------------------ build sheets
P = design.build()
sheets = [Sheet(i, n, t) for i, (n, t) in enumerate(design.SHEETS)]


def cell_sheet(sh, cells):
    sh.text("%s\nEach cell: 18650 holder, red (+) / black (-) test loops, and a zero-drain\n"
            "reverse-insertion indicator (R -> LED -> 1N4148WS). It only conducts if the cell is\n"
            "fitted backwards, so it draws nothing in normal use." % sh.title, 25.4, 22.86, 1.524, True)
    for i, n in enumerate(cells):
        x0 = 30.48 + i * 53.34
        y0 = 68.58
        bt, tpp, tpn = "BT%d" % n, "TP_P%d" % n, "TP_N%d" % n
        r, led, d = "R_REV%d" % n, "LED_REV%d" % n, "D_REV%d" % n
        pos, neg = design.node(n), design.node(n - 1)
        sh.text("CELL %d" % n, x0, y0 - 17.78, 1.524, True)
        sh.place(P[bt], x0 + 5.08, y0 + 20.32, 0, ref_off=(2.54, -1.27), val_off=(2.54, 1.27))
        sh.label(bt, "1", pos, 5.08)
        sh.label(bt, "2", neg, 5.08)
        sh.place(P[d], x0 + 25.4, y0 + 5.08, 270, ref_off=(2.54, -1.27), val_off=(2.54, 1.27))
        sh.place(P[led], x0 + 25.4, y0 + 20.32, 270, ref_off=(2.54, -1.27), val_off=(2.54, 1.27))
        sh.place(P[r], x0 + 25.4, y0 + 35.56, 0, ref_off=(2.54, -1.27), val_off=(2.54, 1.27))
        sh.label(d, "1", pos, 5.08)
        sh.connect(sh.pin(d, "2"), sh.pin(led, "1"))
        sh.connect(sh.pin(led, "2"), sh.pin(r, "1"))
        sh.label(r, "2", neg, 5.08)
        sh.place(P[tpp], x0 + 43.18, y0 + 2.54, 0, ref_off=(2.54, -3.81), val_off=(2.54, -1.27))
        sh.place(P[tpn], x0 + 43.18, y0 + 27.94, 0, ref_off=(2.54, -3.81), val_off=(2.54, -1.27))
        sh.label(tpp, "1", pos, 5.08)
        sh.label(tpn, "1", neg, 5.08)


cell_sheet(sheets[0], range(1, 8))
cell_sheet(sheets[1], range(8, 15))

# ---- BMS interface
s = sheets[2]
s.text("BMS CELL-SENSE HARNESS (J1, JST XH B15B-XH-A, 15 pins)\n"
       "Each tap: 60V-rated PPTC (MF-MSMF010-2) in series, 5V bidirectional TVS across every cell.\n"
       "J1 pin 1 = B- (V0) ... pin 15 = C14+ (V14). Mating housing XHP-15 + SXH-001T-P0.6 crimps.", 25.4, 22.86, 1.524, True)
for k in range(design.NCELLS + 1):
    y = 50.8 + k * 10.16
    f = "F_PTC%d" % (k + 1)
    s.place(P[f], 60.96, y, 90, ref_off=(-3.81, -2.54), val_off=(-3.81, 3.3))
    s.label(f, "1", design.node(k), 5.08)
    s.label(f, "2", "BMS_V%d" % k, 5.08)
for k in range(1, design.NCELLS + 1):
    t = "D_TVS%d" % k
    y = 50.8 + (k - 1) * 10.16 + 5.08
    s.place(P[t], 116.84, y, 0, ref_off=(-3.81, -2.54), val_off=(-3.81, 3.3))
    s.label(t, "1", "BMS_V%d" % (k - 1), 5.08)
    s.label(t, "2", "BMS_V%d" % k, 5.08)
s.place(P["J1"], 177.8, 121.92, 0, ref_off=(-2.54, -21.59), val_off=(-2.54, 21.59))
for k in range(design.NCELLS + 1):
    s.label("J1", str(k + 1), "BMS_V%d" % k, 5.08)

s.text("BMS TEMPERATURE HARNESS (J2, JST XH B14B-XH-A, 14 pins)\n"
       "7x 10k B3950 NTC beads, one saddled between each cell pair, 2 isolated wires each.\n"
       "J2 pin 2n-1 / 2n = NTCn. Mating housing XHP-14.", 215.9, 22.86, 1.524, True)
for i in range(design.NNTC):
    th = "TH%d" % (i + 1)
    y = 55.88 + i * 12.7
    s.place(P[th], 241.3, y, 90, ref_off=(-3.81, -2.54), val_off=(-3.81, 3.3))
    s.label(th, "1", "NTC%d_A" % (i + 1), 5.08)
    s.label(th, "2", "NTC%d_B" % (i + 1), 5.08)
    a, b = design.NTC_CELLS[i]
    s.text("NTC%d: saddle between cell %d and cell %d" % (i + 1, a, b), 264.16, y - 0.635, 1.27)
s.place(P["J2"], 340.36, 109.22, 0, ref_off=(-2.54, -20.32), val_off=(-2.54, 20.32))
for i in range(14):
    s.label("J2", str(i + 1), P["J2"]["pins"][str(i + 1)], 5.08)

# ---- power path
s = sheets[3]
s.text("POWER PATH: CELL_14 -> F1 (5x20mm, 10A) -> PACK+ (J3, M4 lug). PACK- = cell 1 negative (J4, M4 lug).\n"
       "D_TVS_MAIN1 SMCJ70CA clamps pack transients (70V standoff > 58.8V max).", 25.4, 22.86, 1.524, True)
s.place(P["F1"], 76.2, 63.5, 90, ref_off=(-2.54, -3.81), val_off=(-2.54, 3.81))
s.label("F1", "1", design.TOP, 5.08)
s.label("F1", "2", design.PACK_POS, 5.08)
s.place(P["J3"], 160.02, 63.5, 0, ref_off=(-2.54, -7.62), val_off=(-2.54, 7.62))
s.place(P["J4"], 160.02, 93.98, 0, ref_off=(-2.54, -7.62), val_off=(-2.54, 7.62))
for p in "1234":
    s.label("J3", p, design.PACK_POS, 5.08)
    s.label("J4", p, design.PACK_NEG, 5.08)
s.place(P["D_TVS_MAIN1"], 218.44, 78.74, 90, ref_off=(3.81, -1.27), val_off=(3.81, 1.27))
s.label("D_TVS_MAIN1", "1", design.PACK_NEG, 5.08)
s.label("D_TVS_MAIN1", "2", design.PACK_POS, 5.08)

s.text("FUSE-BLOWN INDICATOR: lights amber when F1 is open and a load pulls PACK+ down.", 25.4, 116.84, 1.27, True)
s.place(P["R_FB1"], 50.8, 137.16, 90, ref_off=(-2.54, -3.81), val_off=(-2.54, 3.81))
s.place(P["LED_FB1"], 71.12, 137.16, 180, ref_off=(-2.54, -3.81), val_off=(-2.54, 3.81))
s.label("R_FB1", "1", design.TOP, 5.08)
s.connect(s.pin("R_FB1", "2"), s.pin("LED_FB1", "2"))
s.label("LED_FB1", "1", design.PACK_POS, 5.08)

s.text("HV-PRESENT INDICATOR: LED_HV1 on when PACK+ > ~44V (BZX84C43 + Vbe).\n"
       "R_HV_LED1 22k/1206: 2.6mA, 0.15W at 58.8V.", 203.2, 116.84, 1.27, True)
s.place(P["D_HV1"], 228.6, 142.24, 90, ref_off=(3.81, -1.27), val_off=(3.81, 1.27))
s.label("D_HV1", "3", design.PACK_POS, 2.54)
s.place(P["R_HV_BASE1"], 228.6, 160.02, 0, ref_off=(2.54, -1.27), val_off=(2.54, 1.27))
s.label("D_HV1", "1", "HV_Z_A", 2.54)
s.label("R_HV_BASE1", "1", "HV_Z_A", 2.54)
s.place(P["Q_HV1"], 248.92, 172.72, 0, ref_off=(5.08, -1.27), val_off=(5.08, 1.27))
s.label("R_HV_BASE1", "2", "HV_BASE", 2.54)
s.label("Q_HV1", "1", "HV_BASE", 2.54)
s.place(P["R_HV_PD1"], 238.76, 182.88, 0, ref_off=(2.54, -1.27), val_off=(2.54, 1.27))
s.label("R_HV_PD1", "1", "HV_BASE", 2.54)
s.label("R_HV_PD1", "2", design.PACK_NEG, 2.54)
s.label("Q_HV1", "2", design.PACK_NEG, 5.08)
s.place(P["LED_HV1"], 251.46, 152.4, 270, ref_off=(2.54, -1.27), val_off=(2.54, 1.27))
s.connect(s.pin("LED_HV1", "1"), s.pin("Q_HV1", "3"))
s.place(P["R_HV_LED1"], 251.46, 137.16, 0, ref_off=(2.54, -1.27), val_off=(2.54, 1.27))
s.label("R_HV_LED1", "1", design.PACK_POS, 2.54)
s.connect(s.pin("R_HV_LED1", "2"), s.pin("LED_HV1", "2"))

# ---- mechanical
s = sheets[4]
s.text("MECHANICAL: 6x M3 holes (use nylon standoffs/screws - copper keep-out around each),\n"
       "3x fiducials for JLCPCB SMT assembly.", 25.4, 22.86, 1.524, True)
for i in range(6):
    s.place(P["H%d" % (i + 1)], 50.8 + i * 25.4, 76.2, 0, ref_off=(-2.54, -5.08), val_off=(-2.54, 5.08))
for i in range(3):
    s.place(P["FID%d" % (i + 1)], 50.8 + i * 25.4, 114.3, 0, ref_off=(-2.54, -5.08), val_off=(-2.54, 5.08))

# ------------------------------------------------------------------ write
for sh in sheets:
    open(os.path.join(OUT, sh.name + ".kicad_sch"), "w").write(sh.dump())

root = Sheet(None, "root", "14S BATTERY PACK BREAKOUT - SYSTEM ARCHITECTURE")
root.text("14S 18650 BATTERY PACK ON PCB - BMS BREAKOUT / TRAINING BOARD\n"
          "- Board: A4 landscape 297 x 210 mm, 4-layer\n"
          "- 14 cells in series: 58.8V max / 50.4V nominal / 42V empty (below the 60V SELV limit)\n"
          "- Cell sense: JST XH 15-pin (B-, C1..C14) through 60V PPTCs + per-cell 5V TVS\n"
          "- Temperature: 7x 10k B3950 NTC, one between each pair of cells, JST XH 14-pin\n"
          "- Pack output: M4 lugs PACK+ (after 5x20 10A fuse) and PACK-\n"
          "- Per cell: red/black test loops + reverse-insertion LED", 25.4, 25.4, 1.524, True)
blocks = []
for i, (name, title) in enumerate(design.SHEETS):
    y = 76.2 + i * 33.02
    blocks.append([Sym("sheet"), [Sym("at"), 30.48, y], [Sym("size"), 91.44, 20.32],
                   [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")],
                   [Sym("dnp"), Sym("no")],
                   [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("solid")]],
                   [Sym("fill"), [Sym("color"), 255, 255, 255, 0]], [Sym("uuid"), SHEET_UUID[i]],
                   prop("Sheetname", name, 30.48, y - 1.27, 0, size=1.524, justify="left bottom"),
                   prop("Sheetfile", name + ".kicad_sch", 30.48, y + 21.59, 0, size=1.016, justify="left top"),
                   [Sym("instances"), [Sym("project"), design.PROJECT,
                                       [Sym("path"), "/" + ROOT_UUID, [Sym("page"), str(i + 2)]]]]])
    root.text(title, 127.0, y + 8.89, 1.27)
open(os.path.join(OUT, design.PROJECT + ".kicad_sch"), "w").write(
    root.dump(blocks + [[Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]]]))

# placement metadata for the PCB generator
import json
json.dump({r: dict(uuid=p["uuid"], sheet=p["sheet_uuid"]) for r, p in P.items()},
          open(os.path.join(OUT, "tools", "sch_ids.json"), "w"), indent=0)
print("schematic written:", len(P), "symbols")
