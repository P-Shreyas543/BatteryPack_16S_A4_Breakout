"""Single source of truth for the 14S battery-pack breakout: parts, nets, sheets.

Used by gen_sch.py (schematic) and gen_pcb.py (layout) so both stay in sync.
All LCSC numbers were checked against LCSC/JLCPCB listings (2026-10); re-check
stock before ordering.
"""
from collections import OrderedDict

NCELLS = 14
NNTC = 7
PROJECT = "BatteryPack_16S_A4_Breakout"

PACK_NEG = "PACK_NEG"
PACK_POS = "PACK_POS"
TOP = "CELL_14_UNFUSED"


def node(i):
    """Net name of series node i (0 = pack negative, 14 = top of stack)."""
    if i == 0:
        return PACK_NEG
    if i == NCELLS:
        return TOP
    return "CELL_%d" % i


# ---------------------------------------------------------------- catalogue
FP = {
    "holder": "footprints:BH18650B1BA002",
    "r0805": "Resistor_SMD:R_0805_2012Metric",
    "r1206": "Resistor_SMD:R_1206_3216Metric",
    "led0805": "LED_SMD:LED_0805_2012Metric",
    "sod323": "Diode_SMD:D_SOD-323",
    "sma": "Diode_SMD:D_SMA",
    "smc": "Diode_SMD:D_SMC",
    "sot23": "Package_TO_SOT_SMD:SOT-23",
    "pptc1812": "Fuse:Fuse_1812_4532Metric",
    "ntc": "Resistor_THT:R_Axial_DIN0204_L3.6mm_D1.6mm_P2.54mm_Vertical",
    "xh15": "Connector_JST:JST_XH_B15B-XH-A_1x15_P2.50mm_Vertical",
    "xh14": "Connector_JST:JST_XH_B14B-XH-A_1x14_P2.50mm_Vertical",
    "lug": "footprints:CONN-TH_4P-L11.1-W9.2-P5.00-T44009",
    "fuse5x20": "footprints:FUSE-TH_L24.8-W9.8-P22.60",
    "tp": "TestPoint:TestPoint_Keystone_5000-5004_Miniature",
    "hole": "MountingHole:MountingHole_3.2mm_M3_ISO7380",
    "fid": "Fiducial:Fiducial_1mm_Mask2mm",
}

# (symbol, value, footprint, LCSC, MPN, manufacturer, description)
CAT = {
    "holder": ("Device:Battery_Cell", "18650 holder", FP["holder"], "C2988620",
               "BH-18650-B1BA002", "MYOUNG", "18650 cell holder, SMT, gold-plated phosphor-bronze"),
    "r_rev": ("Device:R", "1k", FP["r0805"], "C17513", "0805W8F1001T5E", "UNI-ROYAL",
              "1k 1% 0805 - reverse-cell LED limit"),
    "led_red": ("Device:LED", "RED", FP["led0805"], "C84256", "NCD0805R1", "NATIONSTAR",
                "Red LED 0805"),
    "led_yel": ("Device:LED", "AMBER", FP["led0805"], "C2296", "KT-0805Y", "Hubei KENTO",
                "Yellow LED 0805"),
    "d_rev": ("Device:D", "1N4148WS", FP["sod323"], "C2128", "1N4148WS", "CJ",
              "75V 150mA switching diode, blocks LED reverse bias"),
    "tp_red": ("Connector:TestPoint", "5000 RED", FP["tp"], "C5199900", "5000", "Keystone",
               "Miniature test loop, red (cell +)"),
    "tp_blk": ("Connector:TestPoint", "5001 BLK", FP["tp"], "C238122", "5001", "Keystone",
               "Miniature test loop, black (cell -)"),
    "pptc": ("Device:Polyfuse", "MF-MSMF010-2 60V/0.1A", FP["pptc1812"], "C12430",
             "MF-MSMF010-2", "BOURNS", "PPTC 60V 100mA hold (rated above 14S max 58.8V)"),
    "tvs5": ("Device:D_TVS", "SMAJ5.0CA", FP["sma"], "C5174731", "SMAJ5.0CA", "JSCJ",
             "400W 5V bidirectional TVS, per-cell sense clamp"),
    "ntc": ("Device:Thermistor_NTC", "10k B3950 1%", FP["ntc"], "C13879", "MF52A103F3950",
            "Nanjing Shiheng", "10k NTC bead, B=3950, saddle between two cells"),
    "xh15": ("Connector_Generic:Conn_01x15", "B15B-XH-A", FP["xh15"], "C158020",
             "B15B-XH-A(LF)(SN)", "JST", "JST XH 2.50mm 15-pin top-entry, BMS cell-sense harness"),
    "xh14": ("Connector_Generic:Conn_01x14", "B14B-XH-A", FP["xh14"], "C158022",
             "B14B-XH-A(LF)(SN)", "JST", "JST XH 2.50mm 14-pin top-entry, BMS NTC harness"),
    "lug": ("Connector_Generic:Conn_01x04", "T44009 M4", FP["lug"], "C481463", "T44009", "XFCN",
            "M4 PCB power terminal (all 4 legs common)"),
    "fuse": ("Device:Fuse", "5x20 holder, fit 10A", FP["fuse5x20"], "C268205", "FH1-200CK-B",
             "HONGJU", "5x20mm fuse clips, 10A max - fit 10A ceramic fast fuse"),
    "tvs70": ("Device:D_TVS", "SMCJ70CA", FP["smc"], "C840779", "SMCJ70CA", "MDD",
              "1500W 70V bidirectional TVS, pack clamp"),
    "zener43": ("Diode:BZX84Cxx", "BZX84C43", FP["sot23"], "C841170", "BZX84C43", "LGE",
                "43V zener, HV-present threshold"),
    "npn_hv": ("Transistor_BJT:Q_NPN_BEC", "MMBTA42", FP["sot23"], "C8515", "MMBTA42", "JSCJ",
               "300V NPN"),
    "r10k": ("Device:R", "10k", FP["r0805"], "C17414", "0805W8F1002T5E", "UNI-ROYAL", "10k 1% 0805"),
    "r47k": ("Device:R", "47k", FP["r0805"], "C17713", "0805W8F4702T5E", "UNI-ROYAL", "47k 1% 0805"),
    "r22k_1206": ("Device:R", "22k 1206", FP["r1206"], "C25830", "1206W4F2202T5E", "UNI-ROYAL",
                  "22k 1% 1206 0.25W (0.15W at 58.8V)"),
    "hole": ("Mechanical:MountingHole", "M3 ISO7380", FP["hole"], "", "", "", "M3 mounting hole, use nylon standoffs"),
    "fid": ("Mechanical:Fiducial", "Fiducial", FP["fid"], "", "", "", "Assembly fiducial"),
}

SHEETS = [
    ("01_Cell_Module_Row1", "CELL MODULE A: CELLS 1 TO 7"),
    ("02_Cell_Module_Row2", "CELL MODULE B: CELLS 8 TO 14"),
    ("03_BMS_Interface_and_Thermal", "BMS INTERFACE: 15-WIRE CELL SENSE + 7x NTC"),
    ("04_Power_Path_and_Protection", "POWER PATH: FUSE, PACK TERMINALS, TVS, INDICATORS"),
    ("05_Mechanical_and_Hardware", "MECHANICAL: MOUNTING HOLES & FIDUCIALS"),
]

# NTC i sits between cells NTC_CELLS[i]; numbered top->bottom, left column then right column
NTC_CELLS = [(1, 2), (3, 4), (5, 6), (7, 8), (13, 14), (11, 12), (9, 10)]


def build():
    parts = OrderedDict()

    def add(ref, kind, pins, sheet, value=None):
        sym, val, fp, lcsc, mpn, mfr, desc = CAT[kind]
        parts[ref] = dict(ref=ref, kind=kind, sym=sym, value=value or val, fp=fp, lcsc=lcsc,
                          mpn=mpn, mfr=mfr, desc=desc, pins=pins, sheet=sheet)

    # ---- cells: holder, +/- test loops, reverse-insertion indicator (R -> LED -> D)
    for n in range(1, NCELLS + 1):
        sh = 0 if n <= 7 else 1
        neg, pos = node(n - 1), node(n)
        add("BT%d" % n, "holder", {"1": pos, "2": neg}, sh)
        add("TP_P%d" % n, "tp_red", {"1": pos}, sh)
        add("TP_N%d" % n, "tp_blk", {"1": neg}, sh)
        add("R_REV%d" % n, "r_rev", {"1": "REV%d_R" % n, "2": neg}, sh)
        add("LED_REV%d" % n, "led_red", {"2": "REV%d_R" % n, "1": "REV%d_D" % n}, sh)  # 1=K 2=A
        add("D_REV%d" % n, "d_rev", {"2": "REV%d_D" % n, "1": pos}, sh)  # 1=K 2=A

    # ---- BMS sense: node -> PPTC -> J1 pin, TVS across adjacent sense lines
    for k in range(0, NCELLS + 1):
        add("F_PTC%d" % (k + 1), "pptc", {"1": node(k), "2": "BMS_V%d" % k}, 2)
    for k in range(1, NCELLS + 1):
        add("D_TVS%d" % k, "tvs5", {"1": "BMS_V%d" % (k - 1), "2": "BMS_V%d" % k}, 2)
    add("J1", "xh15", {str(k + 1): "BMS_V%d" % k for k in range(NCELLS + 1)}, 2)

    # ---- 7 NTC thermistors, 2 wires each, on J2
    j2 = {}
    for i in range(NNTC):
        a, b = "NTC%d_A" % (i + 1), "NTC%d_B" % (i + 1)
        add("TH%d" % (i + 1), "ntc", {"1": a, "2": b}, 2)
        j2[str(2 * i + 1)] = a
        j2[str(2 * i + 2)] = b
    add("J2", "xh14", j2, 2)

    # ---- power path
    add("F1", "fuse", {"1": TOP, "2": PACK_POS}, 3)
    add("J3", "lug", {p: PACK_POS for p in "1234"}, 3, value="PACK+ M4")
    add("J4", "lug", {p: PACK_NEG for p in "1234"}, 3, value="PACK- M4")
    add("D_TVS_MAIN1", "tvs70", {"1": PACK_NEG, "2": PACK_POS}, 3)
    # fuse-blown indicator across F1: lights when cells are live but PACK+ is pulled low
    add("R_FB1", "r47k", {"1": TOP, "2": "FB_LED_A"}, 3)
    add("LED_FB1", "led_yel", {"2": "FB_LED_A", "1": PACK_POS}, 3)
    # HV-present indicator: PACK+ > ~44V lights LED_HV1
    add("D_HV1", "zener43", {"3": PACK_POS, "1": "HV_Z_A"}, 3)  # 1=A 3=K
    add("R_HV_BASE1", "r10k", {"1": "HV_Z_A", "2": "HV_BASE"}, 3)
    add("R_HV_PD1", "r47k", {"1": "HV_BASE", "2": PACK_NEG}, 3)
    add("Q_HV1", "npn_hv", {"1": "HV_BASE", "2": PACK_NEG, "3": "HV_LED_K"}, 3)  # B E C
    add("R_HV_LED1", "r22k_1206", {"1": PACK_POS, "2": "HV_LED_A"}, 3)
    add("LED_HV1", "led_red", {"2": "HV_LED_A", "1": "HV_LED_K"}, 3)

    # ---- mechanical
    for i in range(1, 7):
        add("H%d" % i, "hole", {}, 4)
    for i in range(1, 4):
        add("FID%d" % i, "fid", {}, 4)
    return parts


GLOBAL_NETS = set([node(i) for i in range(NCELLS + 1)] + [PACK_POS])

if __name__ == "__main__":
    p = build()
    nets = {}
    for r, d in p.items():
        for pin, n in d["pins"].items():
            nets.setdefault(n, []).append("%s.%s" % (r, pin))
    for n in sorted(nets):
        print(n, nets[n])
    print(len(p), "parts", len(nets), "nets")
